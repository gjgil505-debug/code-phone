from clipbot.twitch.chat import parse_irc_line


def test_parse_privmsg_with_tags():
    line = ("@badge-info=;display-name=Bob;tmi-sent-ts=1700000000123;user-id=1 "
            ":bob!bob@bob.tmi.twitch.tv PRIVMSG #xqc :KEKW what was that")
    m = parse_irc_line(line)
    assert m.channel == "xqc" and m.user == "bob" and m.text == "KEKW what was that"
    assert abs(m.ts - 1700000000.123) < 1e-6


def test_parse_privmsg_without_tags_uses_now():
    m = parse_irc_line(":amy!amy@amy.tmi.twitch.tv PRIVMSG #summit1g :Pog", now=42.0)
    assert (m.channel, m.user, m.text, m.ts) == ("summit1g", "amy", "Pog", 42.0)


def test_parse_ping_returns_none():
    assert parse_irc_line("PING :tmi.twitch.tv") is None


def test_parse_other_command_returns_none():
    assert parse_irc_line(":tmi.twitch.tv 001 justinfan123 :Welcome, GLHF!") is None
