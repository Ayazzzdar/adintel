"""Trimmed real Ad Library items (shape as returned by the Apify actor)."""

VIDEO_AD = {
    "ad_archive_id": "1869351803954821", "collation_count": 2, "collation_id": "1833204213982697",
    "page_id": "868316096358585", "page_name": "A Day In History USA", "is_active": True,
    "start_date": 1766131200, "end_date": 1790751600,
    "publisher_platform": ["FACEBOOK", "INSTAGRAM"],
    "url": "https://www.facebook.com/adayinhistoryusa/",
    "ad_library_url": "https://www.facebook.com/ads/library/?id=1869351803954821",
    "snapshot": {
        "page_profile_uri": "https://www.facebook.com/adayinhistoryusa/", "page_like_count": 758,
        "page_categories": ["Gifts"], "display_format": "VIDEO", "title": "The Perfect Gift 🎁",
        "body": {"text": "What made headlines the day you were born?\n\nDiscover 50+ facts from your birthdate"},
        "cta_text": "Shop now", "link_url": "https://adayinhistory.co/products/day-you-were-born-pack",
        "cards": [], "images": [],
        "videos": [{"video_hd_url": "https://video.example/v.mp4", "video_sd_url": "https://video.example/sd.mp4",
                    "video_preview_image_url": "https://img.example/preview.jpg"}],
    },
}

DCO_AD = {
    "ad_archive_id": "2027507591518799", "collation_count": 3, "collation_id": "986408960646328",
    "page_id": "1483070478613068", "page_name": "Mapiful", "is_active": True,
    "start_date": 1780383600, "end_date": 1790751600, "publisher_platform": ["FACEBOOK"],
    "url": "https://www.facebook.com/mapiful/",
    "ad_library_url": "https://www.facebook.com/ads/library/?id=2027507591518799",
    "snapshot": {
        "page_profile_uri": "https://www.facebook.com/mapiful/", "page_like_count": 76974,
        "page_categories": ["Gifts"], "display_format": "DCO", "title": "{{product.name}}",
        "body": {"text": "{{product.brand}}"}, "cta_text": "Shop now", "link_url": "http://mapiful.com/",
        "images": [], "videos": [],
        "cards": [{"body": "Graduation, birthdays, anniversaries — celebrate every milestone with a personalized map",
                   "title": "⭐⭐⭐⭐⭐ 2000+ five star reviews!", "link_url": "http://mapiful.com/",
                   "original_image_url": "https://img.example/orig.jpg",
                   "resized_image_url": "https://img.example/resized.jpg"}] * 3,
    },
}

SPAM_AD = {
    "ad_archive_id": "999", "page_id": "890815904120841", "page_name": "Senior Health Insider",
    "is_active": True, "start_date": 1784937600, "end_date": 1790751600,
    "url": "search-url",
    "snapshot": {"display_format": "VIDEO", "title": "Buy 1, Get 1 FREE",
                 "body": {"text": "The day you were born your joints were perfect. Pain relief for over 50s"},
                 "link_url": "https://trybronoir.com/pages/10-reasons", "page_categories": ["Health/beauty"],
                 "cards": [], "images": [], "videos": []},
}
