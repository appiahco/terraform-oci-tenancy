"""Static owner-procedure contracts; never execute the interactive wizard."""
from pathlib import Path
import re
import unittest
import yaml

REPO = Path(__file__).resolve().parents[1]

class BootstrapProcedureTests(unittest.TestCase):
    def test_template_library_is_preserved_and_wizard_is_executable(self):
        template = (REPO / '.agents/skills/wizard/template.sh').read_text()
        wizard_path = REPO / 'scripts/bootstrap-wizard.sh'
        wizard = wizard_path.read_text()
        self.assertEqual(wizard.split('run_wizard() {')[0], template.split('run_wizard() {')[0])
        self.assertTrue(wizard_path.stat().st_mode & 0o111)
        self.assertEqual(len(re.findall(r'^stage "', wizard, re.M)), 12)
        self.assertIn('TOTAL_STAGES=12', wizard)

    def test_environment_secret_destinations_match_workflow(self):
        wizard = (REPO / 'scripts/bootstrap-wizard.sh').read_text().split('run_wizard() {', 1)[1]
        names = set(re.findall(r'^\s*set_secret (\w+)', wizard, re.M))
        expected = {'OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION'}
        self.assertEqual(names, expected)
        workflow = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        for job in ('preflight', 'plan'):
            self.assertEqual(workflow['jobs'][job]['environment'], 'plan')
            refs = set(re.findall(r'secrets\.(OCI_\w+)', str(workflow['jobs'][job])))
            self.assertEqual(refs, expected)
        self.assertIn('--env "$SECRET_ENVIRONMENT"', wizard)
        self.assertIn('install_identity plan plan', wizard)
        self.assertIn('install_identity apply apply-foundation', wizard)
        self.assertIn('install_identity apply apply-workloads', wizard)

    def test_bucket_lifecycle_and_backend_have_no_credential_properties(self):
        resources = (REPO / 'bootstrap/resources.tf').read_text()
        bucket = resources.split('resource "oci_objectstorage_bucket" "state" {')[1].split('resource "')[0]
        self.assertRegex(bucket, r'lifecycle\s*\{\s*prevent_destroy\s*=\s*true')
        backend = (REPO / 'bootstrap/backend.tf').read_text()
        self.assertEqual(set(re.findall(r'^\s*(\w+)\s*=', backend, re.M)), {'key'})
        wizard = (REPO / 'scripts/bootstrap-wizard.sh').read_text().split('run_wizard() {', 1)[1]
        self.assertNotRegex(wizard, r'write_env OCI_PRIVATE_KEY|persist OCI_PRIVATE_KEY')
        reminder = yaml.safe_load((REPO / '.github/workflows/key-rotation.yml').read_text())
        variables = set(re.findall(r'vars\.(\w+)', str(reminder)))
        self.assertEqual(variables, {'OCI_APPLY_ROTATED_ON', 'OCI_PLAN_ROTATED_ON'})
        for name in variables:
            self.assertIn('set_var ' + name, wizard)

    def test_verified_fallback_inputs_take_precedence_on_resume(self):
        wizard = (REPO / 'scripts/bootstrap-wizard.sh').read_text()
        stage = wizard.split('stage "Review public Bootstrap inputs"', 1)[1].split('stage "Owner-reviewed manual Bootstrap apply"', 1)[0]
        # Static data-flow check: read the existing working choice before overwriting inputs.
        self.assertIn('if [[ -f "$WORK_DIR/owner.auto.tfvars.json" ]]; then', stage)
        self.assertIn("print(json.load(open(sys.argv[1]))['iam_exclusion_mode'])", stage)
        self.assertLess(stage.index('PYMODE'), stage.index('write_env IAM_EXCLUSION_MODE'))
        self.assertLess(stage.index('write_env IAM_EXCLUSION_MODE'), stage.index('write_inputs'))
