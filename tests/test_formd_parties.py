from loader.formd_parties import classify, clean_text


def test_entities_lose_na_and_people_stay_people():
    assert classify("n/a Inspired Capital Partners GP I, LLC") == ("entity", "Inspired Capital Partners GP I, LLC")
    assert classify("N/A Hustle Fund Management, LLC") == ("entity", "Hustle Fund Management, LLC")
    assert classify("n/a Acme") == ("entity", "Acme")
    assert classify("Alexa von Tobel") == ("person", "Alexa von Tobel")
    assert classify("Elizabeth Yin") == ("person", "Elizabeth Yin")


def test_relationship_text_quotes():
    assert clean_text(chr(34) + "The General Partner of the Issuer (the " + chr(34) * 2 + "General Partner" + chr(34) * 2 + ")" + chr(34)) ==         "The General Partner of the Issuer (the " + chr(34) + "General Partner" + chr(34) + ")"
    assert clean_text(chr(34) + "Managing Member") == "Managing Member"
    assert clean_text(None) is None
