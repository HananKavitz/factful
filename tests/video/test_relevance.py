"""Tests for the image relevance verification functions."""

from __future__ import annotations

from factful.video.relevance import _extract_nouns, _tokenize, keyword_overlap, noun_jaccard


class TestTokenize:
    def test_lowercases_and_strips_punctuation(self) -> None:
        assert _tokenize("Hello, World!") == ["hello", "world"]

    def test_removes_stopwords(self) -> None:
        result = _tokenize("The rise of AI technology")
        assert "the" not in result
        assert "of" not in result
        assert "rise" in result
        assert "ai" in result
        assert "technology" in result

    def test_empty_string(self) -> None:
        assert _tokenize("") == []

    def test_only_stopwords(self) -> None:
        assert _tokenize("the and of") == []


class TestExtractNouns:
    def test_capitalized_words_are_proper_nouns(self) -> None:
        nouns = _extract_nouns("Apple released iPhone in California")
        assert "apple" in nouns
        assert "iphone" in nouns
        assert "california" in nouns

    def test_common_nouns_are_recognized(self) -> None:
        nouns = _extract_nouns("The research shows interesting results")
        assert "research" in nouns

    def test_unknown_lowercase_words_are_excluded(self) -> None:
        nouns = _extract_nouns("something very flibbertigibbet happened")
        assert "flibbertigibbet" not in nouns
        assert "something" not in nouns

    def test_empty_string(self) -> None:
        assert _extract_nouns("") == set()

    def test_strips_punctuation_before_checking(self) -> None:
        nouns = _extract_nouns("Apple's iPhone.")
        assert "apple's" in nouns or "apples" in nouns or "iphone" in nouns


class TestKeywordOverlap:
    def test_full_match_passes(self) -> None:
        assert keyword_overlap("AI Technology", ["ai", "technology", "computer"])

    def test_partial_match_passes_above_threshold(self) -> None:
        assert keyword_overlap("AI Technology Future", ["ai", "computer", "software"])

    def test_no_match_fails(self) -> None:
        assert not keyword_overlap("AI Technology", ["cooking", "food", "kitchen"])

    def test_empty_heading_passes(self) -> None:
        assert keyword_overlap("", ["anything"])

    def test_heading_with_only_stopwords_passes(self) -> None:
        assert keyword_overlap("the and of", ["anything"])

    def test_case_insensitive_matching(self) -> None:
        assert keyword_overlap("AI", ["Ai", "aRtIfIcIaL"])

    def test_custom_threshold(self) -> None:
        # "AI Technology" → tokens ["ai", "technology"], need 100% match
        assert keyword_overlap("AI Technology", ["ai", "technology"], threshold=1.0)
        assert not keyword_overlap("AI Technology", ["ai"], threshold=1.0)


class TestNounJaccard:
    def test_matching_nouns_passes(self) -> None:
        # heading nouns: {apple, california}
        # desc nouns: {apple, iphone}
        # intersection: {apple}, union: {apple, california, iphone} → 1/3 ≈ 0.33
        assert noun_jaccard("Apple in California", "Apple iPhone released")

    def test_no_overlap_fails(self) -> None:
        assert not noun_jaccard("Microsoft Windows", "Apple iPhone")

    def test_empty_heading_passes(self) -> None:
        assert noun_jaccard("", "anything here")

    def test_none_description_passes(self) -> None:
        assert noun_jaccard("Apple", None)

    def test_description_with_no_nouns_fails_when_heading_has_nouns(self) -> None:
        assert not noun_jaccard("Apple", "the and of")

    def test_custom_threshold(self) -> None:
        # heading nouns: {apple}, desc nouns: {apple} → 1/1 = 1.0
        assert noun_jaccard("Apple", "Apple", threshold=0.9)
        # heading nouns: {apple, california}, desc nouns: {apple, microsoft} → 1/3 ≈ 0.33
        assert not noun_jaccard("Apple California", "Apple Microsoft", threshold=0.9)
