"""Claude-powered ad breakdowns, competitor classification, keyword ideas and remix briefs."""

from typing import List, Literal

import anthropic
from pydantic import BaseModel, Field

from lib import config

MODEL = "claude-opus-5-5"
# Server-side fallback: if a request is ever declined, the API re-runs it on Anthropic's
# recommended fallback model instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(RuntimeError):
    pass


def enabled() -> bool:
    return config.has("ANTHROPIC_API_KEY")


def _client():
    key = config.get("ANTHROPIC_API_KEY")
    if not key:
        raise AIError("ANTHROPIC_API_KEY is not set (add it to Streamlit secrets).")
    return anthropic.Anthropic(api_key=key)


def _ad_content(ad: dict, with_image=True):
    lines = [
        f"Advertiser: {ad.get('page_name')}",
        f"Format: {ad.get('display_format')} ({ad.get('card_count') or 0} cards)",
        f"Running since: {ad.get('start_date')} (active: {ad.get('is_active')})",
        f"Headline: {ad.get('title') or '-'}",
        f"Primary text:\n{ad.get('body') or '-'}",
        f"CTA: {ad.get('cta_text') or '-'}",
        f"Landing page: {ad.get('link_url') or '-'}",
    ]
    content = []
    img = ad.get("image_url") or ad.get("video_preview_url")
    if with_image and img:
        content.append({"type": "image", "source": {"type": "url", "url": img}})
    content.append({"type": "text", "text": "\n".join(lines)})
    return content


def _parse(system, content, schema, max_tokens=8000):
    client = _client()
    try:
        resp = client.beta.messages.parse(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.BadRequestError as e:
        # Ad Library image URLs expire after a few days; retry without the image.
        if any(c.get("type") == "image" for c in content if isinstance(c, dict)):
            return _parse(system, [c for c in content if c.get("type") != "image"], schema, max_tokens)
        raise AIError(f"Claude API rejected the request: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise AIError("Claude API rate limit hit — wait a minute and try again.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Couldn't reach the Claude API (network error).") from e
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise AIError("Claude declined or returned no structured output for this request.")
    return resp.parsed_output


# ---------------------------------------------------------------------------
# 1. Ad breakdown
# ---------------------------------------------------------------------------

Angle = Literal[
    "nostalgia", "perfect gift", "emotional story", "social proof", "offer / discount",
    "urgency / occasion", "problem-solution", "curiosity", "personalisation", "product demo",
    "founder / brand story", "ugc testimonial", "comparison", "humour", "other",
]
CreativeFormat = Literal[
    "static product shot", "lifestyle static", "text-heavy static", "carousel", "catalog / dpa",
    "ugc talking head", "unboxing / reaction video", "product demo video", "slideshow video",
    "meme", "review screenshot", "other",
]
Awareness = Literal["unaware", "problem aware", "solution aware", "product aware", "most aware"]


class AdBreakdown(BaseModel):
    hook: str = Field(description="The first line / first 3 seconds that stops the scroll, quoted or described")
    angle: Angle
    creative_format: CreativeFormat
    offer: str = Field(description="Offer / price / discount / free shipping mentioned, or 'none'")
    awareness: Awareness
    emotion: str = Field(description="Main emotional driver, 1-4 words")
    audience: str = Field(description="Who this ad is clearly aimed at")
    why_it_works: str = Field(description="2-3 sentences on why this ad is likely performing")
    remix_idea: str = Field(description="One sentence: how The Day Archive could adapt this angle")


ANALYST = ("You are a senior direct-response creative strategist who reverse-engineers Meta ads. "
           "Be concrete and specific; never generic. The brand you work for is described below.\n\n")


def analyze_ad(ad: dict, profile: str) -> dict:
    out = _parse(ANALYST + profile, _ad_content(ad) + [
        {"type": "text", "text": "Break this competitor ad down."}], AdBreakdown, 4000)
    return out.model_dump()


# ---------------------------------------------------------------------------
# 2. Discovery helpers
# ---------------------------------------------------------------------------

class Verdict(BaseModel):
    page_id: str
    verdict: Literal["competitor", "adjacent", "irrelevant"]
    reason: str = Field(description="One short sentence")


class Verdicts(BaseModel):
    results: List[Verdict]


def classify_candidates(candidates: list, profile: str) -> list:
    """candidates: dicts with page_id, page_name, landing_domain, sample_title, sample_body."""
    listing = "\n\n".join(
        f"page_id={c['page_id']}\nname={c['page_name']}\ndomain={c.get('landing_domain')}\n"
        f"headline={c.get('sample_title')}\nad text={(c.get('sample_body') or '')[:400]}"
        for c in candidates
    )
    prompt = ("Classify each advertiser below relative to our brand.\n"
              "competitor = sells a similar personalised/sentimental keepsake or gift print;\n"
              "adjacent = same buyer & occasion (gifting, birthdays, personalised décor) but a "
              "different product — useful inspiration;\n"
              "irrelevant = everything else.\n\n" + listing)
    out = _parse(ANALYST + profile, [{"type": "text", "text": prompt}], Verdicts, 8000)
    return [v.model_dump() for v in out.results]


class KeywordIdeas(BaseModel):
    keywords: List[str] = Field(description="Short phrases (2-5 words) people would put in ad copy")


def suggest_keywords(profile: str, sample_copy: list, existing: list) -> list:
    prompt = ("We search the Meta Ad Library by phrase to find advertisers competing with us. "
              "Suggest 10 NEW exact-match phrases likely to appear in competitors' ad copy "
              "(not brand names). Avoid these existing ones: " + ", ".join(existing) +
              "\n\nCopy from competitor ads we already track:\n---\n" + "\n---\n".join(sample_copy[:15]))
    out = _parse(ANALYST + profile, [{"type": "text", "text": prompt}], KeywordIdeas, 3000)
    seen = {k.lower() for k in existing}
    return [k for k in out.keywords if k.lower() not in seen]


# ---------------------------------------------------------------------------
# 3. Remix brief (-> Higgsfield)
# ---------------------------------------------------------------------------

class RemixBrief(BaseModel):
    concept_name: str = Field(description="Short internal name for the concept")
    angle: str = Field(description="The angle we're borrowing and how it maps to our product")
    why_it_works: str
    hooks: List[str] = Field(description="3 scroll-stopping opening lines / on-screen text options")
    headlines: List[str] = Field(description="5 Meta headlines, each under 40 characters")
    primary_text: str = Field(description="Ready-to-paste Meta primary text in our brand voice")
    visual_direction: str = Field(description="What the creative shows, shot by shot or layout by layout")
    image_prompt: str = Field(description=(
        "Prompt for an AI image model for a static ad. The real product photo is supplied as a "
        "reference image, so describe ONLY the scene around it (setting, hands, props, light, "
        "lens, mood) and the overlay text in quotes — never the print's own layout or wording."))
    video_prompt: str = Field(description=(
        "Prompt/script for an AI video model: 10-15s, scene-by-scene with timing, camera moves, "
        "any spoken lines, and on-screen overlay text. The real product photo is supplied as a "
        "reference image, so never describe the print's own layout or wording."))
    recommended_format: Literal["static image", "video", "carousel", "ugc video"]
    aspect_ratio: Literal["4:5", "9:16", "1:1"]


REMIX_RULES = """
Write an ORIGINAL ad for our brand inspired by the reference ad's angle and structure.

Rules:
- Borrow the strategy (angle, hook mechanic, structure, format) — never their brand name,
  logo, product, claims, reviews, characters or exact wording.
- Don't invent review counts, awards, stats or discounts we didn't give you. If an offer helps,
  write it as [OFFER] for us to fill in.

CRITICAL — how to write the image_prompt and video_prompt:
Our real product photo WILL be supplied to the image/video model as a reference image. So:
- Refer to the product as "the product in the reference image" / "the supplied print".
  NEVER describe its layout, section names, headings, fonts, colours or any text printed on it.
  Any such description makes the model invent a fake product that looks nothing like ours.
- Do NOT put a sample birth date, headline, song, price or section list in the prompt.
- Instead, describe only what surrounds the product and how it is shot: the setting, the hands
  or people, props, light, lens, camera move, mood, and the on-screen OVERLAY text (captions
  added on top of the video/image, which are fine to specify and should be in quotes).
- Say explicitly: "keep the print exactly as in the reference image — do not alter, redraw or
  re-letter its contents."
- Keep it realistic, Meta-native and thumb-stopping.
"""


def remix_brief(ad: dict, breakdown: dict | None, profile: str, extra: str = "") -> dict:
    content = _ad_content(ad)
    text = "Reference ad (from a competitor / inspiration brand) is above.\n"
    if breakdown:
        text += f"Our earlier breakdown of it: {breakdown}\n"
    if extra:
        text += f"Extra direction from the team: {extra}\n"
    text += REMIX_RULES
    content.append({"type": "text", "text": text})
    out = _parse(ANALYST + profile, content, RemixBrief, 12000)
    return out.model_dump()


def higgsfield_handoff(brief: dict, brief_id: int, product_refs=None, variations: int = 3) -> str:
    """A message to paste into a Claude session that has the Higgsfield MCP connected."""
    media = "video" if brief.get("recommended_format") in ("video", "ugc video") else "image"
    main_prompt = brief.get("video_prompt") if media == "video" else brief.get("image_prompt")
    refs = [r for r in (product_refs or []) if r]
    if refs:
        ref_block = ("PRODUCT REFERENCE IMAGES (import these and pass them to the model as image "
                     "references — the print must match them exactly):\n"
                     + "\n".join(f"- {u}" for u in refs) + "\n\n")
    else:
        ref_block = ("PRODUCT REFERENCE IMAGES: none saved yet. Ask me to upload photos of the "
                     "real product before generating, or the model will invent a fake print.\n\n")
    return (
        f"Using Higgsfield, create ad creative for The Day Archive — remix brief #{brief_id} "
        f"\"{brief.get('concept_name')}\".\n\n"
        f"Format: {brief.get('recommended_format')}, aspect ratio {brief.get('aspect_ratio')}. "
        f"Generate {variations} variations of the {media}.\n\n"
        f"{ref_block}"
        f"Check the credit cost first and tell me before spending anything.\n"
        f"Keep the product exactly as it appears in the reference images — do not redraw, "
        f"re-letter or restyle the print itself.\n\n"
        f"PROMPT:\n{main_prompt}\n\n"
        f"VISUAL DIRECTION:\n{brief.get('visual_direction')}\n\n"
        + (f"STATIC VERSION PROMPT (also make 2 of these):\n{brief.get('image_prompt')}\n"
           if media == "video" else "")
    )
