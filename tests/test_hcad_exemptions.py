import unittest

from hcad_exemptions import parse

ACCOUNT = '0000000000001'


def fixture(label):
    fields = ['Exemptions and Jurisdictions', 'Exemption Type', 'Districts', 'Jurisdictions',
              'Exemption Value', 'ARB Status', '2025 Rate', '2026 Rate', 'Online Tax Bill',
              label, '001', 'HOUSTON ISD']
    return ('<p>Links to online tax bill information for account <b>' + ACCOUNT + '</b></p>'
            + ''.join('<p>' + field + '</p>' for field in fields))


class ExemptionTests(unittest.TestCase):
    def test_explicit_results_and_unknown(self):
        self.assertIs(parse(fixture('Residential Homestead'), ACCOUNT, 2026)['homestead'], True)
        self.assertIs(parse(fixture('None'), ACCOUNT, 2026)['homestead'], False)
        self.assertIsNone(parse(fixture('Other Exemption'), ACCOUNT, 2026)['homestead'])

    def test_wrong_account_or_year_fails(self):
        for account, year in ((ACCOUNT, 2025), ('0000000000002', 2026)):
            with self.assertRaises(ValueError):
                parse(fixture('None'), account, year)
