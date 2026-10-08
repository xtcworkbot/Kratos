import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bot', Path(__file__).with_name('telegram_bot.py'))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.scope = patch.multiple(bot, PRIVATE=tmp, DB=tmp/'state.sqlite3', SETTINGS=tmp/'execution_settings.json')
        self.scope.start()
        self.addCleanup(self.scope.stop)
        bot.initialise()
        self.b = bot.Bot({'token': 'fake', 'owner': '123'})
        self.sent = []
        self.b.send = lambda text: self.sent.append(text) or {'message_id': 100}

    def msg(self, uid=1, owner=123, text='Hello', kind='private'):
        return {'update_id': uid, 'message': {'message_id': uid, 'chat': {'id': owner, 'type': kind},
                'from': {'id': owner}, 'text': text}}

    def test_reject_others_groups_and_impersonation(self):
        self.b.accept(self.msg(owner=456))
        self.b.accept(self.msg(uid=2, kind='group'))
        forged=self.msg(uid=3); forged['message']['from']['id']=456
        self.b.accept(forged)
        with bot.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
        self.assertEqual(bot.get('offset'), 4)

    def test_queue_is_durable_and_duplicate_update_is_ignored(self):
        self.b.accept(self.msg())
        self.b.accept(self.msg())
        with bot.connect() as db:
            self.assertEqual(db.execute('SELECT prompt,status FROM jobs').fetchall(), [('Hello','queued')])
        self.assertEqual(bot.get('offset'), 2)

    def test_reset_preserves_history_and_project(self):
        bot.put('session', 'test-session')
        self.b.accept(self.msg(text='/new'))
        self.b.control(1, '/new')
        self.assertIsNone(bot.get('session'))
        with bot.connect() as db:
            self.assertEqual(db.execute('SELECT sid FROM sessions').fetchone()[0], 'test-session')

    def test_reset_refuses_during_work(self):
        bot.put('session', 'keep-me')
        self.b.busy=True
        self.b.control(1, '/new')
        self.assertEqual(bot.get('session'), 'keep-me')

    def test_stop_cancels_queued_tasks(self):
        self.b.accept(self.msg())
        self.b.accept(self.msg(uid=2,text='/stop'))
        self.b.control(2, '/stop')
        with bot.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM jobs ORDER BY id').fetchall(), [('cancelled',),('done',)])

    def test_no_inherited_environment_credentials(self):
        with patch.dict(bot.os.environ, {'SOME_SECRET': 'dummy', 'OPENAI_API_KEY': 'dummy',
                                         'ANTHROPIC_API_KEY': 'dummy', 'GITHUB_TOKEN': 'dummy'}):
            env = bot.model_env()
        for key in ('SOME_SECRET', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GITHUB_TOKEN'):
            self.assertNotIn(key, env)

    def test_project_is_this_folder_and_canonical_context_loaded(self):
        self.assertEqual(bot.PROJECT, Path(__file__).resolve().parents[1])
        cmd = bot.claude_command()
        prompt = cmd[cmd.index('--system-prompt') + 1]
        self.assertIn(f'You are {bot.NAME}', prompt)
        self.assertIn((bot.PROJECT / 'AGENTS.md').read_text(), prompt)
        self.assertIn((bot.PROJECT / 'NOW.md').read_text(), prompt)

    def test_model_scope_and_sandboxed_shell_without_inherited_integrations(self):
        cmd=bot.claude_command('abc')
        self.assertEqual(cmd[cmd.index('--model')+1], bot.MODEL)
        self.assertEqual(cmd[cmd.index('--effort')+1], bot.EFFORT)
        self.assertIn('--restricted',cmd)
        self.assertIn('--safe-mode',cmd)
        self.assertIn('--strict-mcp-config',cmd)
        self.assertIn('Bash',cmd[cmd.index('--tools')+1])
        self.assertEqual(cmd[cmd.index('--allowedTools')+1], 'WebSearch,WebFetch,Bash')
        self.assertEqual(cmd[cmd.index('--system-prompt-snapshot')+1], 'off')
        self.assertEqual(cmd[cmd.index('--max-turns')+1], '60')
        settings=json.loads(Path(cmd[cmd.index('--settings')+1]).read_text())
        self.assertTrue(settings['sandbox']['enabled'])
        self.assertTrue(settings['sandbox']['failIfUnavailable'])
        self.assertFalse(settings['sandbox']['allowUnsandboxedCommands'])
        self.assertIn(str(bot.PROJECT), settings['sandbox']['filesystem']['allowRead'])
        self.assertIn(str(bot.HERE), settings['sandbox']['filesystem']['denyWrite'])
        self.assertIn(f'Edit(/{bot.HERE}/**)', settings['permissions']['deny'])
        self.assertEqual(cmd[-2:],['--resume','abc'])

    def test_repeated_tool_calls_stop_and_duplicate_events_do_not_count(self):
        guard=bot.ToolGuard()
        for i in range(3):
            event={'message':{'content':[{'type':'tool_use','id':str(i),'name':'Bash','input':{'command':'false'}}]}}
            self.assertIsNone(guard.observe(event))
            self.assertIsNone(guard.observe(event))
        event['message']['content'][0]['id']='4'
        self.assertEqual(guard.observe(event),'repeated_tool_call')
        self.assertEqual(len(guard.tools),4)

    def test_repeated_errors_stop_and_success_resets_streak(self):
        guard=bot.ToolGuard()
        event={'message':{'content':[{'type':'tool_result','is_error':True}]}}
        for _ in range(4):self.assertIsNone(guard.observe(event))
        self.assertEqual(guard.observe(event),'repeated_tool_errors')
        guard.observe({'message':{'content':[{'type':'tool_result','is_error':False}]}})
        self.assertEqual(guard.consecutive_errors,0)

    def test_tool_budget_stops_different_calls(self):
        guard=bot.ToolGuard()
        with patch.object(bot,'MAX_TOOL_CALLS',2):
            for i in range(2):
                self.assertIsNone(guard.observe({'message':{'content':[{'type':'tool_use','id':str(i),'name':'Read','input':{'file_path':str(i)}}]}}))
            self.assertEqual(guard.observe({'message':{'content':[{'type':'tool_use','id':'last','name':'Read','input':{}}]}}),'tool_limit')

    def test_real_stalled_process_is_stopped_by_job_deadline(self):
        import sys
        from unittest.mock import MagicMock
        self.b.accept(self.msg(text='deadline test'))
        with bot.connect() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=1")
        command=[sys.executable,'-c','import sys,time; sys.stdin.read(); time.sleep(60)']
        self.b.busy=True
        with patch.object(bot,'JOB_TIMEOUT_SECONDS',0.15), patch.object(bot,'claude_command',return_value=command), patch.object(bot,'Preview',return_value=MagicMock()):
            self.b.run_job(1,'deadline test')
        self.assertFalse(self.b.busy)
        self.assertIsNone(self.b.proc)
        with bot.connect() as db:
            self.assertEqual(db.execute('SELECT outcome,reason FROM executions WHERE id=1').fetchone(),('stopped','time_limit'))
            self.assertIn('Nothing will retry automatically',db.execute('SELECT reply FROM jobs WHERE id=1').fetchone()[0])

if __name__=='__main__': unittest.main()
