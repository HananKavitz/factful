import pytest
from sqlalchemy.exc import IntegrityError

from factful.db import build_engine, init_db, session_factory
from factful.models import Story, User


def _fresh_session():
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    return session_factory(engine)


def test_user_email_is_unique() -> None:
    sessions = _fresh_session()
    with sessions() as db:
        db.add(User(google_sub="sub-1", email="a@example.com", name="Alice"))
        db.commit()
        db.add(User(google_sub="sub-2", email="a@example.com", name="Bob"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_user_google_sub_is_unique() -> None:
    sessions = _fresh_session()
    with sessions() as db:
        db.add(User(google_sub="sub-1", email="a@example.com", name="Alice"))
        db.commit()
        db.add(User(google_sub="sub-1", email="b@example.com", name="Bob"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_story_requires_user() -> None:
    sessions = _fresh_session()
    with sessions() as db:
        db.add(Story(user_id=999, prompt="Chips", title="Chips", markdown="# Chips"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_user_style_profile_roundtrip() -> None:
    sessions = _fresh_session()
    with sessions() as db:
        user = User(
            google_sub="sub-1",
            email="a@example.com",
            name="Alice",
            style_profile='{"name": "voice"}',
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        assert user.style_profile == '{"name": "voice"}'


def test_user_style_profile_defaults_to_none() -> None:
    user = User(google_sub="sub-1", email="a@example.com", name="Alice")
    assert user.style_profile is None


def test_updated_at_changes_on_update() -> None:
    sessions = _fresh_session()
    with sessions() as db:
        user = User(google_sub="sub-1", email="a@example.com", name="Alice")
        db.add(user)
        db.commit()
        story = Story(user_id=user.id, prompt="Chips", title="Chips", markdown="# Chips")
        db.add(story)
        db.commit()
        db.refresh(story)
        created = story.created_at
        story.markdown = "# Chips\n\nUpdated."
        db.commit()
        db.refresh(story)
        assert story.created_at == created
        assert story.updated_at >= created


def test_owned_stories_query() -> None:
    sessions = _fresh_session()
    with sessions() as db:
        alice = User(google_sub="sub-1", email="a@example.com", name="Alice")
        bob = User(google_sub="sub-2", email="b@example.com", name="Bob")
        db.add_all([alice, bob])
        db.commit()
        db.add_all(
            [
                Story(user_id=alice.id, prompt="A1", title="A1", markdown="# A1"),
                Story(user_id=alice.id, prompt="A2", title="A2", markdown="# A2"),
                Story(user_id=bob.id, prompt="B1", title="B1", markdown="# B1"),
            ]
        )
        db.commit()
        from sqlalchemy import select

        alice_stories = db.scalars(
            select(Story)
            .where(Story.user_id == alice.id)
            .order_by(Story.created_at.desc(), Story.id.desc())
        ).all()
        assert [s.prompt for s in alice_stories] == ["A2", "A1"]
