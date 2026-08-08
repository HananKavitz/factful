from factful.verify.bm25 import Bm25Scorer, index_passages, tokenize
from factful.verify.passages import split_passages


def test_split_passages_splits_on_sentence_end() -> None:
    text = "The market grew. Revenue hit $4B. Analysts expect 9% growth."
    assert split_passages(text) == [
        "The market grew.",
        "Revenue hit $4B.",
        "Analysts expect 9% growth.",
    ]


def test_split_passages_keeps_decimals_intact() -> None:
    assert split_passages("Revenue grew 4.2% last quarter.") == ["Revenue grew 4.2% last quarter."]


def test_split_passages_collapses_whitespace() -> None:
    assert split_passages("Line one.\n\n   Line two with  spaces.") == [
        "Line one.",
        "Line two with spaces.",
    ]


def test_split_passages_empty_text() -> None:
    assert split_passages("   \n\n  ") == []


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("Revenue hit $4.2B in 2024!") == [
        "revenue",
        "hit",
        "4",
        "2b",
        "in",
        "2024",
    ]


def test_bm25_deterministic_scores() -> None:
    passages = [
        "Revenue grew 12 percent in the semiconductor market.",
        "The market size reached four trillion dollars.",
        "Analysts forecast 9% growth for the whole industry.",
    ]
    scorer = Bm25Scorer(passages=passages)
    hits = scorer.retrieve("semiconductor revenue market", k=3)
    assert [h.passage for h in hits] == [
        "Revenue grew 12 percent in the semiconductor market.",
        "The market size reached four trillion dollars.",
    ]


def test_bm25_retrieves_best_passage_first() -> None:
    passages = [
        "The company paid $4B for the startup.",
        "Weather in the valley turned cold overnight.",
        "Analysts expect the market to grow steadily.",
    ]
    hits = Bm25Scorer(passages=passages).retrieve("company paid startup", k=3)
    assert hits[0].passage == "The company paid $4B for the startup."
    assert hits[0].score > 0.0


def test_bm25_respects_top_k() -> None:
    passages = [
        "Revenue hit $4B in 2024.",
        "Market grew 9% last year.",
        "Jobs rose to 2.1 million.",
        "Output doubled in a decade.",
    ]
    hits = Bm25Scorer(passages=passages).retrieve("revenue market jobs", k=2)
    assert len(hits) == 2
    assert all(h.score > 0.0 for h in hits)


def test_bm25_no_overlap_returns_empty() -> None:
    hits = Bm25Scorer(passages=["about cats", "about dogs"]).retrieve("quantum physics", k=3)
    assert hits == []


def test_bm25_empty_corpus_returns_empty() -> None:
    assert index_passages([]).retrieve("anything", k=3) == []


def test_index_passages_helper() -> None:
    scorer = index_passages(["revenue grew 12%", "market declined"])
    assert len(scorer.retrieve("revenue grew", k=1)) == 1
