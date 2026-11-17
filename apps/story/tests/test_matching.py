from story_app.matching import LexicalMatcher, tokens

LET_IN = "Let him in open the door, help him, be kind, let the stranger inside"
TURN_AWAY = "Turn him away keep the door shut, send him away, don't trust him"


def scores(msg):
    return LexicalMatcher().scores(msg, [LET_IN, TURN_AWAY])


def test_contractions_and_stopwords_are_ignored():
    assert tokens("He's freezing, don't you think?") == {"freez", "think"}


def test_long_messages_still_match():
    let_in, turn_away = scores("let him in, he's freezing")
    assert let_in >= 0.5 > turn_away


def test_best_option_wins_and_option_numbers_work():
    let_in, turn_away = scores("keep the door shut")
    assert turn_away == 1.0 and let_in < turn_away
    assert scores("2") == [0.0, 1.0]
    assert scores("hello there") == [0.0, 0.0]
