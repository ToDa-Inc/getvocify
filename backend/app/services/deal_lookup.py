"""
Deal lookup service for Option C: match extraction to deals, disambiguate on approval.
Orchestrates HubSpot matching and builds WhatsApp disambiguation flow.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from supabase import Client

from app.logging_config import log_domain, DOMAIN_HUBSPOT
from app.models.approval import DealMatch
from app.models.memo import MemoExtraction
from app.services.crm_config import CRMConfigurationService
from app.services.hubspot import HubSpotClient, HubSpotMatchingService, HubSpotSearchService

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE_THRESHOLD = 0.9
MATCH_LIMIT = 3


@dataclass
class LookupResult:
    """Result of deal lookup: action and optional disambiguation data."""

    action: str  # "create_new" | "confirm_one" | "disambiguate"
    matches: list[DealMatch] = ()
    message: Optional[str] = None  # WhatsApp message for confirm_one / disambiguate

    @property
    def deal_options(self) -> list[dict]:
        """List of {deal_id, deal_name} for state."""
        return [{"deal_id": m.deal_id, "deal_name": m.deal_name} for m in self.matches]

    @property
    def new_deal_index(self) -> int:
        """1-based index for 'create new' option in reply mapping."""
        if self.action == "confirm_one":
            return 2  # 1=update, 2=new
        return len(self.matches) + 1  # 1..N deals, N+1=new


class DealLookupService:
    """
    Runs deal matching and Option C disambiguation.
    Call run_lookup before approval; on reply use resolve_choice.
    """

    def __init__(self, supabase: Client) -> None:
        self.supabase = supabase
        self.config_service = CRMConfigurationService(supabase)

    async def run_lookup(
        self,
        extraction: MemoExtraction,
        user_id: str,
    ) -> LookupResult:
        """
        Find matching deals and determine Option C action.
        Returns create_new if no HubSpot or no matches; otherwise confirm_one or disambiguate.
        """
        try:
            conn_result = (
                self.supabase.table("crm_connections")
                .select("*")
                .eq("user_id", user_id)
                .eq("provider", "hubspot")
                .eq("status", "connected")
                .limit(1)
                .execute()
            )
            if not conn_result.data:
                logger.info(
                    "Deal lookup: no HubSpot connection",
                    extra=log_domain(DOMAIN_HUBSPOT, "lookup_no_connection", user_id=user_id),
                )
                return LookupResult(action="create_new")

            config = await self.config_service.get_configuration(user_id)
            pipeline_id = config.default_pipeline_id if config else None

            client = HubSpotClient(conn_result.data[0]["access_token"])
            search_service = HubSpotSearchService(client)
            matching_service = HubSpotMatchingService(client, search_service)

            matches = await matching_service.find_matching_deals(
                extraction,
                limit=MATCH_LIMIT,
                pipeline_id=pipeline_id,
            )

            if not matches:
                logger.info(
                    "Deal lookup: no matches",
                    extra=log_domain(DOMAIN_HUBSPOT, "lookup_no_matches", user_id=user_id),
                )
                return LookupResult(action="create_new")

            top = matches[0]
            if len(matches) == 1 and top.match_confidence >= HIGH_CONFIDENCE_THRESHOLD:
                msg = f"Found {top.deal_name}. Reply 1 to update, 2 to create new."
                return LookupResult(
                    action="confirm_one",
                    matches=matches,
                    message=msg,
                )

            parts = [f"Reply {i+1} for {m.deal_name}" for i, m in enumerate(matches)]
            parts.append(f"{len(matches)+1} for new deal.")
            msg = "Found deals:\n" + "\n".join(parts)
            return LookupResult(
                action="disambiguate",
                matches=matches,
                message=msg,
            )

        except Exception as e:
            logger.warning(
                "Deal lookup failed, falling back to create new: %s",
                e,
                extra=log_domain(DOMAIN_HUBSPOT, "lookup_failed", user_id=user_id, error=str(e)),
            )
            return LookupResult(action="create_new")

    def resolve_choice(
        self,
        choice: int,
        deal_options: list[dict],
        new_deal_index: int,
    ) -> tuple[Optional[str], bool]:
        """
        Map user reply (1, 2, 3...) to deal_id or is_new_deal.
        Returns (deal_id, is_new_deal). Fallback to create new on invalid choice.
        """
        if choice == new_deal_index:
            return (None, True)
        idx = choice - 1
        if 0 <= idx < len(deal_options):
            return (deal_options[idx].get("deal_id"), False)
        return (None, True)
