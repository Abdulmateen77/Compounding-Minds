"""News via Firecrawl: parsing, relevance, caching and the number guard (no network, no model)."""
import json
from datetime import date

from research import web

RAW = {"success": True, "creditsUsed": 2, "data": {"news": [
    {"title": "Tesla cuts capital spending to about $20 billion", "url": "https://www.reuters.com/a", "date": "2 days ago",
     "snippet": "![img](http://x/y.png) Tesla cut its [capital spending](https://x) forecast to roughly $20 billion on Wednesday."},
    {"title": "Tesla cuts capital spending to about $20 billion", "url": "https://finance.yahoo.com/dup", "date": "2 days ago", "snippet": "dup"},
    {"title": "Best pizza in Austin", "url": "https://example.com/pizza", "date": "1 day ago", "snippet": "Tesla is mentioned here"},
    {"title": "Tesla shares rise", "url": "https://www.wsj.com/old", "date": "3 months ago", "snippet": "old"},
    {"title": "TSLA stock slips after earnings", "url": "https://www.cnbc.com/b", "date": "5 hours ago", "snippet": "Shares fell 3% in late trading."}]}}


def test_age_and_snippet_cleaning():
    assert web.age_days("3 days ago") == 3 and web.age_days("2 weeks ago") == 14 and web.age_days("5 hours ago") == 0
    assert web.age_days("Oct 22, 2026") is None
    assert web.clean("# Head\n![i](http://a.png) See [the report](http://b.com) now") == "Head See the report now"
    assert web.short_name("Tesla, Inc.") == "Tesla" and web.short_name("Coca Cola Co") == "Coca Cola"


def test_only_relevant_recent_distinct_articles_are_kept_newest_first(tmp_path):
    got = web.fetch("Tesla, Inc.", "TSLA", date(2026, 10, 24), runner=lambda a: RAW, cache_dir=tmp_path)
    titles = [i["title"] for i in got["items"]]
    assert titles == ["TSLA stock slips after earnings", "Tesla cuts capital spending to about $20 billion"]
    assert got["items"][1]["source"] == "reuters.com" and "![" not in got["items"][1]["text"]
    assert got["credits_used"] == 2


def test_a_second_request_the_same_day_is_served_from_disk(tmp_path):
    calls = []
    run = lambda a: calls.append(a) or RAW                                       # noqa: E731
    web.fetch("Tesla, Inc.", "TSLA", date(2026, 10, 24), runner=run, cache_dir=tmp_path)
    again = web.fetch("Tesla, Inc.", "TSLA", date(2026, 10, 24), runner=run, cache_dir=tmp_path)
    assert len(calls) == 1 and again["items"]


def test_no_firecrawl_or_a_failed_search_means_no_news_not_an_error(tmp_path):
    assert web.fetch("Tesla, Inc.", "TSLA", runner=lambda a: None, cache_dir=tmp_path) is None
    assert web.build(None, "Tesla, Inc.", "TSLA", runner=lambda a: None, cache_dir=tmp_path) is None


class _Gw:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, agent, messages, **kw):
        return self.reply


def _news(tmp_path):
    return web.fetch("Tesla, Inc.", "TSLA", date(2026, 10, 24), runner=lambda a: RAW, cache_dir=tmp_path)


def test_a_line_must_point_at_an_article_and_use_only_that_articles_numbers(tmp_path):
    news = _news(tmp_path)           # article 1 = the 3% one, article 2 = the $20 billion one
    reply = json.dumps({"items": [
        {"n": 2, "text": "Reuters reports Tesla cut capital spending to about 20 billion dollars."},        # 20 is in article 2
        {"n": 1, "text": "CNBC says shares fell 3% in late trading."},                                       # 3 is in article 1
        {"n": 1, "text": "CNBC says the stock may reach 500."},                                              # invented number
        {"n": 2, "text": "Reuters says shares fell 3%."},                                                     # a number from another article
        {"n": 9, "text": "No such article."}, {"text": "no n"}]})
    lines = web.summarise(_Gw(reply), "Tesla", news)
    assert [l["source"] for l in lines] == ["reuters.com", "cnbc.com"]
    assert lines[0]["url"] == "https://www.reuters.com/a"


def test_bad_model_output_gives_no_lines(tmp_path):
    news = _news(tmp_path)
    assert web.summarise(_Gw("not json"), "Tesla", news) == [] and web.summarise(_Gw("{}"), "Tesla", news) == []
    assert web.summarise(_Gw("{}"), "Tesla", None) == []
