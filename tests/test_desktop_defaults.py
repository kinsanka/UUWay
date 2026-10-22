"""Security boundaries of the optional login-lock installer; no live PAM calls."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import uuway_desktop as desktop
import uuway_desktop_system as system


class DesktopDefaults(unittest.TestCase):
    def test_greetd_preserves_the_greeter(self):
        old = '[terminal]\nvt=2\n[default_session]\ncommand="existing-greeter"\nuser="greeter"\n'
        new = system.greetd_config(old, 'alice')
        self.assertTrue(new.startswith(old))
        self.assertIn('user = "alice"', new)
        self.assertEqual(new, system.greetd_config(new, 'alice'))

    def test_existing_login_keeps_gpu_environment(self):
        old = '[initial_session]\nuser="alice"\ncommand="/usr/bin/env WLR_DRM_NO_ATOMIC=1 /usr/bin/start-umbriel"\n'
        self.assertEqual(system.greetd_config(old, 'alice'), old)

    def test_other_user_and_other_desktop_are_not_replaced(self):
        for user, command in [('bob', '/usr/bin/start-umbriel'), ('alice', '/usr/bin/gnome-session')]:
            with self.assertRaises(ValueError):
                system.greetd_config('[initial_session]\nuser='+json.dumps(user)+'\ncommand='+json.dumps(command), 'alice')

    def test_keyring_module_cannot_weaken_password_authentication(self):
        old = 'auth substack system-auth\nauth include postlogin\nauth optional pam_gnome_keyring.so\naccount include system-auth\n'
        new = system.login_pam(old)
        self.assertTrue(new.startswith('auth substack system-auth\nauth include postlogin\n'))
        self.assertIn('auth optional pam_gnome_keyring.so auto_start', new)
        self.assertEqual(new, system.login_pam(new))

    def test_custom_pam_control_is_preserved_by_refusal(self):
        for control in ['sufficient', 'required', '[success=done default=ignore]']:
            with self.assertRaises(ValueError):
                system.login_pam('auth '+control+' pam_gnome_keyring.so\n')
        with self.assertRaises(ValueError):
            system.login_pam('auth optional pam_gnome_keyring.so only_if=gdm\n')

    def test_missing_keyring_module_is_added_after_existing_auth(self):
        old = 'auth required pam_unix.so\naccount required pam_unix.so\n'
        new = system.login_pam(old)
        self.assertTrue(new.startswith(old))
        self.assertEqual(new.count('pam_gnome_keyring.so'), 1)

    def test_settings_keep_existing_hooks_and_unrelated_keys(self):
        old = '[hooks]\nstarted="owner-command"\n[lockscreen]\nfingerprint=true\n[theme]\nmode="dark"\n'
        new = desktop.set_table(old, 'lockscreen', {'fingerprint':False, 'grace_period_seconds':0})
        self.assertIn('started="owner-command"', new)
        self.assertIn('mode="dark"', new)
        self.assertEqual(new, desktop.set_table(new, 'lockscreen', {'fingerprint':False, 'grace_period_seconds':0}))

    def test_unlocked_keyring_prompt_is_never_closed(self):
        with patch.object(desktop,'status',return_value=False), patch.object(desktop,'run') as action:
            desktop.clear_prompts()
            action.assert_not_called()

    def test_lock_prompt_cleanup_rechecks_unlock_and_ignores_other_windows(self):
        windows = [dict(id='user-app',app_id='editor',title='Unlock Login Keyring'),
                   dict(id='keyring',app_id='gcr-prompter',title='Unlock Login Keyring')]
        with patch.object(desktop,'status',side_effect=[True,False]), patch.object(desktop,'run',return_value=subprocess.CompletedProcess([],0,stdout=json.dumps(windows))) as action:
            desktop.clear_prompts()
            self.assertEqual(action.call_count,1)  # Only queried; did not close after unlock.

    def test_guard_does_not_lock_again_on_a_bridge_restart(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'marker';marker.write_text('{"phase":"existing-session"}')
            with patch.object(desktop,'session_marker',return_value=marker),patch.object(desktop,'run') as action:
                desktop.guard();action.assert_not_called()

    def test_guard_requires_confirmed_lock_before_recording_ready(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'marker'
            with patch.object(desktop,'session_marker',return_value=marker),patch.object(desktop,'marker_phase',side_effect=[None,'lock-confirmed']),patch.object(desktop,'run') as action:
                desktop.guard()
                self.assertFalse(marker.exists())  # Only the confirmed-lock hook writes it.
                self.assertEqual(action.call_args.args[0],['/usr/bin/noctalia','msg','session','lock'])

    def test_pending_lock_status_does_not_authorize_startup(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'marker'
            with patch.object(desktop,'session_marker',return_value=marker),patch.object(desktop,'status',return_value=True),patch.object(desktop.time,'monotonic',side_effect=[0,0,26]),patch.object(desktop.time,'sleep'),patch.object(desktop,'run') as action:
                with self.assertRaises(RuntimeError):desktop.guard()
                self.assertFalse(marker.exists())
                self.assertEqual(action.call_args.args[0],['/usr/bin/umbriel','msg','session-quit'])

    def test_failed_startup_lock_returns_to_greeter_and_does_not_mark_ready(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'marker'
            with patch.object(desktop,'session_marker',return_value=marker),patch.object(desktop.time,'monotonic',side_effect=[0,26]),patch.object(desktop,'run') as action:
                with self.assertRaises(RuntimeError):desktop.guard()
                self.assertFalse(marker.exists())
                self.assertEqual(action.call_args.args[0],['/usr/bin/umbriel','msg','session-quit'])


if __name__ == '__main__':
    unittest.main()
