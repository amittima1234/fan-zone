"""Manual scraping and ingestion trigger endpoints."""

import logging
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import get_ai_service, get_article_repository
from db.repository import ArticleRepository
from schemas.feed import IngestionTriggerResponse
from services.ai_worker import AIEnrichmentService, FallbackAIEnrichmentService
from services.scrapers import (
    SCRAPER_REGISTRY,
    get_all_scrapers,
    get_scraper,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/trigger",
    response_model=IngestionTriggerResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger on-demand scraping and enrichment pipeline",
    description="Manually execute web scraping, AI enrichment, and database persistence for a specific publisher or all portals.",
)
async def trigger_ingestion(
    publisher: Optional[str] = Query(
        default=None,
        description="Target publisher identifier (e.g. 'sport5', 'ynet', 'one') or 'all'. Omit to scrape all portals.",
    ),
    limit: Optional[int] = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of articles to scrape per portal.",
    ),
    repo: ArticleRepository = Depends(get_article_repository),
    ai_service: Union[AIEnrichmentService, FallbackAIEnrichmentService] = Depends(get_ai_service),
) -> IngestionTriggerResponse:
    """Execute scraping pipeline, enrich new articles with AI, and persist to database."""
    # 1. Validate publisher if specified
    target_publisher = publisher.strip().lower() if publisher and publisher.strip() else None

    if target_publisher and target_publisher != "all":
        if target_publisher not in SCRAPER_REGISTRY:
            available = list(SCRAPER_REGISTRY.keys())
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid publisher '{publisher}'. Available publishers: {available}",
            )

    # 2. Select scrapers to execute
    if target_publisher and target_publisher != "all":
        scrapers = [get_scraper(target_publisher)]
    else:
        scrapers = get_all_scrapers()

    articles_fetched = 0
    articles_queued = 0
    errors: List[str] = []

    # 3. Execute scrape and enrichment pipeline
    for scraper in scrapers:
        pub_id = getattr(scraper, "publisher_id", "unknown")
        try:
            raw_articles = await scraper.scrape(limit=limit)
            articles_fetched += len(raw_articles)

            for raw_article in raw_articles:
                url_str = str(raw_article.url).strip()
                try:
                    # Deduplicate before enrichment to avoid redundant AI calls
                    if await repo.exists_by_url(url_str):
                        logger.debug("Article already exists in DB, skipping: %s", url_str)
                        continue

                    # Enrich and persist
                    if hasattr(ai_service, "enrich_and_store"):
                        await ai_service.enrich_and_store(raw_article, repo)
                    else:
                        enriched = await ai_service.enrich_article(raw_article)
                        await repo.create_enriched_article(raw_article, enriched)

                    articles_queued += 1
                except Exception as art_err:
                    err_msg = f"Failed to enrich/save article '{url_str}': {art_err}"
                    logger.warning(err_msg)
                    errors.append(err_msg)

        except Exception as scraper_err:
            err_msg = f"Scraper execution failed for '{pub_id}': {scraper_err}"
            logger.error(err_msg)
            errors.append(err_msg)

    # 4. Construct trigger response
    pub_label = target_publisher or "all"
    status_str = "completed" if not errors or articles_queued > 0 else "failed"
    message = (
        f"Ingestion run completed for '{pub_label}': "
        f"fetched {articles_fetched} articles, saved {articles_queued} new articles."
    )

    return IngestionTriggerResponse(
        status=status_str,
        publisher=pub_label,
        articles_fetched=articles_fetched,
        articles_queued=articles_queued,
        message=message,
        errors=errors if errors else None,
    )
