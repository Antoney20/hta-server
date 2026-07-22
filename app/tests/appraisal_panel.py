from uuid import UUID

from django.test import TestCase

from app.models import (
    CriteriaAppraisalTool,
    InterventionProposal,
)

from app.services.appraisal_panel import AppraisalPanelService


class AppraisalPanelServiceTests(TestCase):

    def setUp(self):
        self.criterion = CriteriaAppraisalTool.objects.create(
            criteria="Burden of Disease",
            headers=[
                {"key": "evidence", "label": "Evidence"},
                {"key": "source", "label": "Source"},
            ],
            active=True,
        )

    def test_list_criteria(self):
        result = AppraisalPanelService.list_criteria({})

        print("\n=== First 10 Criteria ===")
        for i, criterion in enumerate(result["data"][:10], start=1):
            print(f"{i}. {criterion['id']} | {criterion['criteria']} | active={criterion['active']}")
        print("=========================\n")

        self.assertTrue(result["ok"])

    def test_get_criterion(self):
        result = AppraisalPanelService.get_criterion(self.criterion.id)

        self.assertTrue(result["ok"])
        self.assertEqual(UUID(result["data"]["id"]), self.criterion.id)

    def test_invalid_headers(self):
        result = AppraisalPanelService.create_criterion({
            "criteria": "Test",
            "headers": "wrong type"
        })

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "headers must be a list")