
import hashlib
import json
from datetime import datetime, timezone

from app.db.session import get_db
from app.models import Company, SourceDocument


COLLECTION_DATE = "2026-11-09"


COMPETITORS = [
    {
        "name": "Spotify",
        "website": "https://www.spotify.com/",
        "industry": "Music and audio streaming",
        "description": (
            "Music and audio streaming platform with individual, "
            "Duo, Family, and Student subscription offerings."
        ),
        "sources": [
            {
                "url": "https://newsroom.spotify.com/spotify-timeline/",
                "title": "Spotify: A Visual History",
                "publisher": "Spotify",
                "source_type": "official_blog",
                "publication_date": None,
                "content_text": (
                    "Spotify: A Visual History. "
                    "March 2014: Spotify adds Family and Student plans, "
                    "because sharing is caring."
                ),
            },
            {
                "url": (
                    "https://newsroom.spotify.com/2019-08-19/"
                    "upgraded-spotify-premium-family-plan-value-the-"
                    "entire-household-will-love/"
                ),
                "title": (
                    "Upgraded Spotify Premium Family Plan: "
                    "Value the Entire Household Will Love"
                ),
                "publisher": "Spotify",
                "source_type": "official_blog",
                "publication_date": "2019-08-19",
                "content_text": (
                    "August 19, 2019. With our updated plan, Spotify "
                    "Premium Family subscribers have on-demand access "
                    "to 450,000 podcast titles and 50 million tracks "
                    "of ad-free music. Parents will now be able to "
                    "control the Explicit Content Filter setting of "
                    "all other accounts on their plan. "
                    "The update is now available in Ireland and will "
                    "rollout in all markets with Premium Family this "
                    "fall. Family Mix: Families will get exclusive "
                    "access to a personalized playlist packed with "
                    "songs the whole family enjoys. Family Hub: "
                    "Billing users can now manage their Family's "
                    "settings in one place, including adding or "
                    "removing family members, keeping their home "
                    "address up to date, and adjusting parental "
                    "controls. Spotify Premium Family still provides "
                    "six individual Spotify Premium accounts for "
                    "family members living under one roof."
                ),
            },
            {
                "url": (
                    "https://newsroom.spotify.com/2019-10-30/"
                    "introducing-spotify-kids-a-new-standalone-app-"
                    "for-the-next-generation-of-listeners/"
                ),
                "title": (
                    "Introducing Spotify Kids, A New Standalone App "
                    "for the Next Generation of Listeners"
                ),
                "publisher": "Spotify",
                "source_type": "official_blog",
                "publication_date": "2019-10-30",
                "content_text": (
                    "October 30, 2019. Spotify Kids is a standalone "
                    "app available exclusively for Premium Family "
                    "subscribers and intended for kids ages 3+. "
                    "The content is ad-free and hand-picked by a "
                    "team of editors. Each kid can select a custom "
                    "avatar and color theme to personalize their "
                    "experience. Spotify Kids is available starting "
                    "today in Ireland. Spotify Premium Family master "
                    "account holders can download Kids from the "
                    "App Store or Google Play."
                ),
            },
            {
                "url": (
                    "https://newsroom.spotify.com/2023-07-24/"
                    "adjusting-our-spotify-premium-prices/"
                ),
                "title": "Adjusting Our Spotify Premium Prices",
                "publisher": "Spotify",
                "source_type": "official_blog",
                "publication_date": "2023-07-24",
                "content_text": (
                    "July 24, 2023. Spotify announced Premium price "
                    "changes across a number of markets. Spotify "
                    "stated that the market landscape had continued "
                    "to evolve since launch and that the updates "
                    "would help it continue delivering value to "
                    "fans and artists. In the United States, the "
                    "announced Premium Family price was $16.99."
                ),
            },
        ],
    },
    {
        "name": "Disney+",
        "website": "https://www.disneyplus.com/",
        "industry": "Video streaming and entertainment",
        "description": (
            "Subscription video streaming service operated by "
            "The Walt Disney Company."
        ),
        "sources": [
            {
                "url": (
                    "https://thewaltdisneycompany.com/app/uploads/"
                    "2019/03/Disney_Investor_Day_2019_transcript.pdf"
                ),
                "title": "Disney Investor Day 2019 Transcript",
                "publisher": "The Walt Disney Company",
                "source_type": "investor_presentation",
                "publication_date": "2019-04-11",
                "content_text": (
                    "Disney Investor Day 2019. The presentation "
                    "describes personalized viewing experiences "
                    "and states: for every subscription, consumers "
                    "will also be able to set up multiple profiles "
                    "to distinguish family members using the "
                    "service. The presentation also describes "
                    "parental controls."
                ),
            },
            {
                "url": (
                    "https://thewaltdisneycompany.com/news/"
                    "ad-supported-disney-plan-launches-with-more-"
                    "than-100-advertisers/"
                ),
                "title": (
                    "Ad-Supported Disney+ Plan Launches with "
                    "More Than 100 Advertisers"
                ),
                "publisher": "The Walt Disney Company",
                "source_type": "press_release",
                "publication_date": "2022-12-08",
                "content_text": (
                    "December 8, 2022. Today, Disney+ made its "
                    "highly anticipated ad-supported subscription "
                    "offering available in the U.S., with more than "
                    "100 advertisers across all major categories "
                    "at launch. Disney+ Basic subscribers can "
                    "create up to seven profiles per account, "
                    "with profile PINs and content ratings through "
                    "Parental Controls. Subscribers can stream on "
                    "up to four supported devices simultaneously."
                ),
            },
            {
                "url": (
                    "https://help.disneyplus.com/en-GB/article/"
                    "disneyplus-en-li-subscription-sharing"
                ),
                "title": "Sharing Your Disney+ Subscription",
                "publisher": "Disney+ Help Center",
                "source_type": "other",
                "publication_date": "2026-05-21",
                "content_text": (
                    "May 21, 2026. Disney+ cannot be shared outside "
                    "of your Household. A Household is a collection "
                    "of devices associated with your primary personal "
                    "residence that are used by the individuals who "
                    "reside there. People outside of your Household "
                    "can sign up for their own account or can be "
                    "added as an Extra Member. Disney+ automatically "
                    "detects and establishes a Household based on "
                    "subscription activity, linked devices, and "
                    "internet connection among other factors."
                ),
            },
            {
                "url": (
                    "https://help.disneyplus.com/en-GB/article/"
                    "disneyplus-en-pl-introduction"
                ),
                "title": "Getting Started with Disney+",
                "publisher": "Disney+ Help Center",
                "source_type": "other",
                "publication_date": None,
                "content_text": (
                    "Disney+ allows subscribers to create up to "
                    "seven profiles for their Household. Disney+ "
                    "offers parental controls including Junior "
                    "Mode, profile PIN protection, and content "
                    "ratings. A subscription allows simultaneous "
                    "streaming on multiple devices. A subscription "
                    "is designated for use within a single "
                    "Household, with an Extra Member add-on "
                    "available for one additional person outside "
                    "the Household."
                ),
            },
        ],
    },
    {
        "name": "YouTube",
        "website": "https://www.youtube.com/",
        "industry": "Video streaming and digital media",
        "description": (
            "Online video platform offering advertising-supported "
            "content and paid memberships including YouTube Premium "
            "and YouTube Music Premium."
        ),
        "sources": [
            {
                "url": (
                    "https://blog.youtube/news-and-events/"
                    "youtube-music-and-youtube-premium/"
                ),
                "title": (
                    "YouTube Music and YouTube Premium Launch "
                    "in 17 Countries: It's All Here"
                ),
                "publisher": "The YouTube Team",
                "source_type": "official_blog",
                "publication_date": "2018-06-18",
                "content_text": (
                    "June 18, 2018. YouTube Premium also launches "
                    "today. Starting today, YouTube Premium, "
                    "formerly YouTube Red, will be available in "
                    "17 countries. The announcement listed a "
                    "United States Family Plan price of $17.99 "
                    "per month. Current YouTube Red and Google "
                    "Play Music members, including family plans, "
                    "in the U.S., Australia, New Zealand, and "
                    "Mexico would automatically receive access "
                    "to YouTube Premium at their current price."
                ),
            },
            {
                "url": (
                    "https://support.google.com/youtube/answer/"
                    "7507349?hl=en"
                ),
                "title": "Sign Up for and Manage a YouTube Family Plan",
                "publisher": "YouTube Help",
                "source_type": "other",
                "publication_date": None,
                "content_text": (
                    "YouTube family plans allow membership benefits "
                    "to be shared with up to five other family "
                    "members who live within the same residential "
                    "address. Family members use their own Google "
                    "accounts and have their own personal libraries, "
                    "subscriptions, and recommendations. The family "
                    "manager is the primary account holder and can "
                    "invite or remove family members. Family groups "
                    "share access to YouTube Premium and YouTube "
                    "Music Premium."
                ),
            },
            {
                "url": (
                    "https://support.google.com/youtube/answer/"
                    "15976004?hl=en"
                ),
                "title": (
                    "Set Up a YouTube Premium or YouTube Music "
                    "Premium Two-Person Plan"
                ),
                "publisher": "YouTube Help",
                "source_type": "other",
                "publication_date": None,
                "content_text": (
                    "YouTube Two-person plans allow membership "
                    "benefits to be shared with one other member "
                    "who lives in the same household. The family "
                    "manager is the primary account holder, pays "
                    "for the membership, and manages adding and "
                    "removing members. The shared member uses "
                    "their own Google account and has their own "
                    "personal library, subscriptions, and "
                    "recommendations. The Two-person plan is "
                    "currently available in India, among other "
                    "listed countries."
                ),
            },
        ],
    },
]


def _content_hash(content: str) -> str:
    normalized = " ".join(content.split())
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _parse_publication_date(value: str | None):
    if not value:
        return None

    return datetime.strptime(
        value,
        "%Y-%m-%d",
    ).replace(tzinfo=timezone.utc)


def _get_or_create_company(db, data):
    company = (
        db.query(Company)
        .filter(Company.name == data["name"])
        .first()
    )

    if company:
        return company, False

    company = Company(
        name=data["name"],
        website=data["website"],
        industry=data["industry"],
        description=data["description"],
    )

    db.add(company)
    db.flush()

    return company, True


def _get_or_create_source(db, company, data):
    source = (
        db.query(SourceDocument)
        .filter(
            SourceDocument.company_id == company.id,
            SourceDocument.url == data["url"],
        )
        .first()
    )

    if source:
        return source, False

    content = data["content_text"]

    source = SourceDocument(
        company_id=company.id,
        url=data["url"],
        title=data["title"],
        publisher=data["publisher"],
        source_type=data["source_type"],
        publication_date=_parse_publication_date(
            data["publication_date"]
        ),
        collected_at=datetime.now(timezone.utc),
        content_text=content,
        content_hash=_content_hash(content),
        permission_status="public",
        reliability=None,
        processing_status="pending",
        source_metadata={
            "collection_method": "manual_official_source_research",
            "collection_version": "competitor_family_research_v1",
            "collection_date": COLLECTION_DATE,
            "content_scope": "relevant_source_excerpt",
            "original_source_url": data["url"],
        },
    )

    db.add(source)
    db.flush()

    return source, True


def seed_competitors():
    generator = get_db()
    db = next(generator)

    summary = {
        "companies_created": 0,
        "companies_existing": 0,
        "sources_created": 0,
        "sources_existing": 0,
        "competitors": [],
    }

    try:
        for competitor_data in COMPETITORS:
            company, company_created = _get_or_create_company(
                db,
                competitor_data,
            )

            if company_created:
                summary["companies_created"] += 1
            else:
                summary["companies_existing"] += 1

            competitor_result = {
                "company_name": company.name,
                "company_id": company.id,
                "sources": [],
            }

            for source_data in competitor_data["sources"]:
                source, source_created = _get_or_create_source(
                    db,
                    company,
                    source_data,
                )

                if source_created:
                    summary["sources_created"] += 1
                else:
                    summary["sources_existing"] += 1

                competitor_result["sources"].append({
                    "source_id": source.id,
                    "title": source.title,
                    "status": (
                        "created" if source_created else "already_exists"
                    ),
                    "processing_status": source.processing_status,
                })

            summary["competitors"].append(competitor_result)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
        generator.close()

    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    seed_competitors()
