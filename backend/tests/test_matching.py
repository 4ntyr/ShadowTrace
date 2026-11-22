from app.ingest.attribution import extract_countries, is_criminal
from app.ingest.matcher import GroupMatcher
from app.ingest.textintel import detect_countries, detect_effect


def test_matcher_against_real_aliases(db):
    m = GroupMatcher.from_db(db)

    def names(text):
        from app.models import Group
        return sorted(db.get(Group, x.group_id).name for x in m.match(text))

    assert names("Sandworm hits Ukrainian grid again") == ["Sandworm Team"]
    assert names("Fancy Bear and Cozy Bear both active") == ["APT28", "APT29"]
    assert names("A snake was found in the server room") == []
    assert names("Researchers analyse Snake malware variant") == ["Turla"]
    assert names("Cobalt Strike beacons everywhere") == []
    assert names("Comment on the latest patch Tuesday") == []
    assert names("Midnight Blizzard targets diplomats") == ["APT29"]
    assert names("Gonjeshke Darande claims attack") == ["Predatory Sparrow"]


def test_attribution_extraction():
    assert extract_countries("Axiom is a suspected Chinese cyber espionage group that has targeted Russia.") == ["CN"]
    assert extract_countries("X is a threat group that has been attributed to Russia's GRU.") == ["RU"]
    assert extract_countries("Machete is a suspected Spanish-speaking cyber espionage group.") == []
    assert extract_countries("SideCopy is a Pakistani threat group that has primarily targeted Indian personnel.") == ["PK"]
    assert is_criminal("FIN7 is a financially-motivated threat group")


def test_text_intel():
    assert "UA" in detect_countries("Attack on Ukraine's energy grid")
    assert "GE" not in detect_countries("Hackers hit a utility in Atlanta, Georgia")
    assert detect_effect("New wiper deployed against banks") == "disruptive"
    assert detect_effect("DDoS wave hits airports") == "ddos"
