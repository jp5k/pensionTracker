"""Cost guardrail: an AWS Budgets alert emailed before spend gets out of hand.

Budgets don't *stop* spending; they warn. The first two budgets in an account
are free.
"""

from typing import Any

from aws_cdk import Stack
from aws_cdk import aws_budgets as budgets
from constructs import Construct

#: Monthly budget in USD (AWS bills in USD). Expected spend is under $1/month.
MONTHLY_LIMIT_USD = 10


class BudgetStack(Stack):
    """A monthly cost budget with two email alerts.

    * 80% of the limit actually spent this month.
    * 100% of the limit *forecast* to be spent by month end, which fires
      earlier, while there's still time to react.
    """

    def __init__(self, scope: Construct, construct_id: str, *, alert_email: str,
                 **kwargs: Any) -> None:
        """Create the budget.

        Args:
            scope: Parent construct (the CDK app).
            construct_id: Logical name of this stack.
            alert_email: Where alerts go. Passed in via CDK context rather than
                committed to the repo.
            **kwargs: Standard ``Stack`` options.
        """
        super().__init__(scope, construct_id, **kwargs)

        subscribers = [
            budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email)
        ]

        def alert(notification_type: str, threshold: int) -> (
                budgets.CfnBudget.NotificationWithSubscribersProperty):
            """Build one alert rule: fire when spend exceeds ``threshold``% of the limit."""
            return budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type=notification_type,
                    comparison_operator="GREATER_THAN",
                    threshold=threshold,
                    threshold_type="PERCENTAGE",
                ),
                subscribers=subscribers,
            )

        # There's no high-level (L2) construct for Budgets, so this uses the
        # L1 "Cfn" class, which maps 1:1 onto the CloudFormation resource
        # AWS::Budgets::Budget.
        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name="pension-tracker-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=MONTHLY_LIMIT_USD, unit="USD"
                ),
            ),
            notifications_with_subscribers=[
                alert("ACTUAL", 80),
                alert("FORECASTED", 100),
            ],
        )
