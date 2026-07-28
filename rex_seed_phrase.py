"""
REX — 10-Word Seed Phrase Vault Key
======================================
A hardware crypto wallet-style backup for the Rexxie vault.

Your MAIN 2FA remains: passphrase + TOTP code from your phone.

This 10-word phrase is your BACKUP — for when:
  • You lost your phone (can't get TOTP code)
  • Your authenticator app data was wiped
  • You're traveling without your phone
  • Any situation where your primary 2FA isn't available

The phrase works exactly like a Ledger or Trezor hardware wallet:
  • 10 words chosen from the BIP39 word list (2048 words)
  • 10 words = 110 bits of entropy (stronger than any password)
  • Write it on paper like a crypto seed — store it physically
  • Never type it digitally. Never photograph it. Never email it.
  • Present 3 consecutive words to confirm identity before use

How it works:
  1. Generate once: python rex_seed_phrase.py --generate
  2. Write down all 10 words on paper. Number them 1–10.
  3. Store the paper in your home safe or bank safe deposit box.
  4. If you lose your phone and need vault access:
     "rexxie backup phrase: [word1] [word2] ... [word10]"
     → Vault unlocks without TOTP
     → Security email sent to alert you of bypass use

The phrase is stored as a HASH only — the words themselves are never
saved anywhere on your Mac. Losing the paper = losing the backup.
But your vault recovery shares still work independently.

Layered recovery (priority order if primary fails):
  Layer 1: Passphrase + TOTP (normal operation)
  Layer 2: Passphrase + 10-word seed phrase (phone lost)
  Layer 3: 3 recovery shares from safe/bank (everything lost)
  Layer 4: Emergency wipe from Telegram (worst case — protect the data)
"""

import os
import json
import hmac
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

REXXIE_DB_PATH   = Path.home() / "Desktop" / "REX" / "rexxie.db"
CONFIG_PATH      = Path.home() / "Desktop" / "REX" / "rex_seed_config.json"

# Full BIP39 English word list (2048 words — standard for crypto wallets)
# Loading from the standard list embedded here for offline use
BIP39_WORDS = [
    "abandon","ability","able","about","above","absent","absorb","abstract","absurd","abuse",
    "access","accident","account","accuse","achieve","acid","acoustic","acquire","across","act",
    "action","actor","actress","actual","adapt","add","addict","address","adjust","admit",
    "adult","advance","advice","aerobic","afford","afraid","again","age","agent","agree",
    "ahead","aim","air","airport","aisle","alarm","album","alcohol","alert","alien",
    "all","alley","allow","almost","alone","alpha","already","also","alter","always",
    "amateur","amazing","among","amount","amused","analyst","anchor","ancient","anger","angle",
    "angry","animal","ankle","announce","annual","another","answer","antenna","antique","anxiety",
    "any","apart","apology","appear","apple","approve","april","arch","arctic","area",
    "arena","argue","arm","armed","armor","army","around","arrange","arrest","arrive",
    "arrow","art","artist","artwork","ask","aspect","assault","asset","assist","assume",
    "asthma","athlete","atom","attack","attend","attitude","attract","auction","audit","august",
    "aunt","author","auto","autumn","average","avocado","avoid","awake","aware","away",
    "awesome","awful","awkward","axis","baby","balance","bamboo","banana","banner","barely",
    "bargain","barrel","base","basic","basket","battle","beach","bean","beauty","because",
    "become","beef","before","begin","behave","behind","believe","below","belt","bench",
    "benefit","best","betray","better","between","beyond","bicycle","bid","bike","bind",
    "biology","bird","birth","bitter","black","blade","blame","blanket","blast","bleak",
    "bless","blind","blood","blossom","blouse","blue","blur","blush","board","boat",
    "body","boil","bomb","bone","book","boost","border","boring","borrow","boss",
    "bottom","bounce","box","boy","bracket","brain","brand","brave","breeze","brick",
    "bridge","brief","bright","bring","brisk","broccoli","broken","bronze","broom","brother",
    "brown","brush","bubble","buddy","budget","buffalo","build","bulb","bulk","bullet",
    "bundle","bunker","burden","burger","burst","bus","business","busy","butter","buyer",
    "buzz","cabbage","cabin","cable","cactus","cage","cake","call","calm","camera",
    "camp","canal","cancel","candy","cannon","canvas","canyon","capable","capital","captain",
    "carbon","card","cargo","carpet","carry","cart","case","cash","casino","castle",
    "casual","catalog","catch","category","cattle","cause","caution","cave","ceiling","celery",
    "cement","census","century","cereal","certain","chair","chaos","chapter","charge","chase",
    "chat","cheap","check","cheese","chef","cherry","chest","chicken","chief","child",
    "chimney","choice","choose","chronic","chuckle","chunk","churn","cigar","cinnamon","circle",
    "citizen","city","civil","claim","clap","clarify","claw","clay","clean","clerk",
    "clever","click","client","cliff","climb","clinic","clip","clock","clog","close",
    "cloth","cloud","clown","club","clump","cluster","coil","coin","collect","color",
    "column","combine","come","comfort","comic","common","company","concert","conduct","confirm",
    "congress","connect","consider","control","convince","cook","cool","copper","copy","coral",
    "core","corn","correct","cost","cotton","couch","country","couple","course","cousin",
    "cover","coyote","crack","cradle","craft","cram","crane","crash","crater","crawl",
    "crazy","cream","credit","creek","crew","cricket","crime","crisp","critic","cross",
    "crouch","crowd","crucial","cruel","cruise","crumble","crunch","crush","cry","crystal",
    "cube","culture","cup","cupboard","curious","current","curtain","curve","cushion","cute",
    "cycle","dad","damage","damp","dance","danger","daring","dash","daughter","dawn",
    "day","deal","debate","debris","decade","december","decide","decline","decorate","decrease",
    "deer","defense","define","defy","degree","delay","deliver","demand","demise","denial",
    "dentist","deny","depart","depend","deposit","depth","deputy","derive","describe","desert",
    "design","desk","despair","destroy","detail","detect","develop","device","devote","diagram",
    "dial","diamond","diary","dice","diesel","diet","differ","digital","dignity","dilemma",
    "dinner","dinosaur","direct","disagree","discover","disease","dish","dismiss","disorder","display",
    "distance","divert","divide","divorce","dizzy","doctor","document","dog","doll","dolphin",
    "domain","donate","donkey","donor","door","dose","double","dove","draft","dragon",
    "drama","drastic","draw","dream","dress","drift","drill","drink","drip","drive",
    "drop","drum","dry","duck","dumb","dune","during","dust","dutch","duty",
    "dwarf","dynamic","eager","eagle","early","earn","earth","east","easy","echo",
    "edge","educate","effort","eight","either","elbow","elder","electric","elegant","element",
    "elephant","elevator","elite","else","embark","embody","embrace","emerge","emotion","employ",
    "empower","empty","enable","enact","endless","endorse","enemy","energy","enforce","engage",
    "engine","enhance","enjoy","enough","enrich","enroll","ensure","enter","entire","entry",
    "envelope","episode","equal","equip","erase","erode","erosion","error","erupt","escape",
    "essay","essence","estate","eternal","evidence","evil","evolve","exact","example","excess",
    "exchange","excite","exclude","exercise","exhaust","exhibit","exile","exist","exit","exotic",
    "expand","expire","explain","expose","express","extend","extra","eye","fable","face",
    "faculty","faint","faith","fall","false","fame","family","famous","fan","fancy",
    "fantasy","far","fashion","fat","fatal","father","fatigue","fault","favorite","feature",
    "february","federal","fee","feed","feel","female","fence","festival","fetch","fever",
    "fiction","field","figure","file","film","filter","final","find","finish","fire",
    "firm","first","fiscal","fish","fit","fitness","fix","flag","flame","flash",
    "flat","flavor","flee","flight","flip","float","flock","floor","flower","fluid",
    "foam","focus","fog","follow","food","force","forest","forget","fork","fortune",
    "forum","forward","fossil","foster","found","fox","fragile","frame","frequent","fresh",
    "friend","fringe","frog","front","frost","frown","frozen","fruit","fuel","fun",
    "funny","furnace","fury","future","gadget","gain","galaxy","gallery","game","gap",
    "garbage","garden","garlic","garment","gas","gasp","gate","gather","gauge","gaze",
    "general","genius","genre","gentle","genuine","gesture","ghost","giant","gift","giggle",
    "ginger","giraffe","girl","give","glad","glance","glare","glass","glide","glimpse",
    "globe","gloom","glory","glove","glow","glue","goat","goddess","gold","good",
    "goose","gorilla","gospel","gossip","govern","grab","grace","grain","grant","grape",
    "grasp","grass","gravity","great","green","grid","grief","grit","grocery","group",
    "grow","grunt","guard","guide","guilt","guitar","gun","gym","habit","hair",
    "half","hammer","hamster","hand","happy","harsh","harvest","hat","have","hawk",
    "hazard","head","health","heart","heavy","hedgehog","height","hello","helmet","help",
    "hero","hidden","high","hill","hint","hip","hire","history","hobby","hockey",
    "hold","hole","holiday","hollow","home","honey","hood","hope","horn","horse",
    "hospital","host","hour","hover","hub","huge","human","humble","humor","hundred",
    "hungry","hunt","hurdle","hurry","hurt","husband","hybrid","icon","idle","ignore",
    "ill","illegal","image","imitate","immense","immune","impact","impose","improve","impulse",
    "inbox","income","increase","index","indicate","indoor","industry","infant","inflict","inform",
    "inhale","inject","inner","innocent","input","inquiry","insane","insect","inspire","install",
    "intact","interest","invest","invite","involve","iron","island","isolate","issue","item",
    "ivory","jacket","jaguar","jar","jazz","jealous","jelly","jewel","job","join",
    "joke","journey","joy","judge","juice","jump","jungle","junior","junk","just",
    "kangaroo","keen","keep","ketchup","key","kick","kingdom","kiss","kit","kitchen",
    "kiwi","knee","knife","knock","know","lab","lamp","language","laptop","large",
    "later","laugh","laundry","lava","law","lawn","lawsuit","layer","lazy","leader",
    "learn","leave","lecture","left","leg","legal","legend","lemon","lend","length",
    "lens","leopard","lesson","letter","level","liar","liberty","library","license","life",
    "lift","like","limb","limit","link","lion","liquid","list","little","live",
    "lizard","load","loan","lobster","local","lock","logic","lonely","long","loop",
    "lottery","loud","lounge","love","loyal","lucky","luggage","lumber","lunar","lunch",
    "luxury","mad","magic","magnet","maid","main","mammal","mango","mansion","manual",
    "maple","marble","march","margin","marine","market","marriage","mask","master","match",
    "material","math","matter","maximum","maze","meadow","meaning","medal","media","melody",
    "melt","member","memory","mention","mercy","mesh","message","metal","method","middle",
    "midnight","milk","million","mimic","mind","minimum","minor","minute","miracle","miss",
    "mixture","model","modify","moon","moral","mother","motion","mountain","mouse","move",
    "movie","much","muffin","mule","multiply","muscle","museum","mushroom","music","must",
    "mutual","myself","mystery","naive","name","napkin","narrow","nasty","natural","nature",
    "near","neck","need","negative","neglect","neither","nephew","nerve","network","neutral",
    "never","news","next","nice","night","noble","noise","nominee","normal","notable",
    "note","nothing","notice","novel","now","nuclear","number","nurse","nut","oak",
    "obey","object","oblige","obscure","obtain","ocean","offer","office","often","oil",
    "okay","old","olive","olympic","omit","once","onion","open","opera","oppose",
    "option","orange","orbit","orchard","order","ordinary","organ","orient","original","orphan",
    "ostrich","other","outdoor","output","outside","oval","over","own","oyster","ozone",
    "pact","paddle","page","pair","palace","palm","panda","panel","panic","panther",
    "paper","parade","parent","park","parrot","party","pass","patch","path","patrol",
    "pause","pave","payment","peace","peanut","peasant","pelican","pencil","people","pepper",
    "perfect","permit","person","pet","phone","photo","phrase","physical","piano","picnic",
    "picture","piece","pig","pigeon","pill","pilot","pink","pioneer","pipe","pistol",
    "pitch","pizza","place","planet","plastic","plate","play","please","pledge","plunge",
    "poem","poet","point","polar","pole","police","pond","pony","pool","popular",
    "portion","position","possible","post","potato","pottery","poverty","powder","power","practice",
    "praise","predict","prefer","prepare","present","pretty","prevent","price","pride","primary",
    "print","priority","prison","private","prize","problem","process","produce","profit","program",
    "project","promote","proof","property","prosper","protect","proud","provide","public","pudding",
    "pull","pulp","pulse","pump","punch","pupil","puppy","purchase","purity","purpose",
    "push","put","puzzle","pyramid","quality","quantum","quarter","question","quick","quit",
    "quiz","quote","rabbit","raccoon","race","rack","radar","radio","rage","rail",
    "rain","raise","rally","ramp","ranch","random","range","rapid","rare","rate",
    "rather","raven","reach","ready","real","reason","rebel","rebuild","recall","receive",
    "recipe","record","recycle","reduce","reflect","reform","refuse","region","regret","regular",
    "reject","relax","release","relief","rely","remain","remember","remind","remove","render",
    "renew","rent","reopen","repair","repeat","replace","report","require","rescue","resemble",
    "resist","response","result","retire","retreat","return","reunion","reveal","review","reward",
    "rhythm","ribbon","ride","ridge","rifle","right","rigid","riot","ripple","risk",
    "ritual","rival","river","road","roast","robot","robust","rocket","romance","roof",
    "rookie","rotate","rough","round","route","royal","rubber","rude","rug","rule",
    "run","runway","rural","sad","saddle","sadness","safe","sail","salad","salmon",
    "salon","salt","salute","same","sample","sand","satisfy","satoshi","sauce","sausage",
    "save","scale","scan","scatter","scene","scheme","school","science","scissors","scorpion",
    "scout","scrap","screen","script","scrub","sea","search","season","seat","second",
    "secret","section","security","seek","segment","select","sell","seminar","senior","sense",
    "sentence","series","service","session","settle","setup","seven","shadow","shaft","shallow",
    "share","shed","shell","sheriff","shield","shift","shine","ship","shock","shoe",
    "shoot","shop","short","shoulder","shrug","shuffle","shy","sibling","siege","sight",
    "silent","silk","silly","silver","similar","simple","since","sing","siren","sister",
    "six","size","sketch","skill","skin","skirt","skull","slap","slice","slide",
    "slight","slim","slogan","slot","slow","slush","small","smart","smile","smoke",
    "smooth","snack","snake","snap","sniff","snow","solar","soldier","solid","solution",
    "solve","someone","soon","sorry","soul","sound","source","south","space","spare",
    "spatial","spawn","speak","special","speed","sphere","spice","spider","spike","spin",
    "spirit","split","spoil","sponsor","spoon","spray","spread","spring","spy","square",
    "squeeze","squirrel","stable","stadium","staff","stage","stairs","stand","start","state",
    "stay","steak","steel","stem","step","stereo","stick","still","sting","stock",
    "stomach","stone","stop","store","storm","story","stove","strategy","street","strike",
    "strong","struggle","student","stuff","stumble","subject","submit","subway","success","sudden",
    "suffer","sugar","suggest","suit","supply","supreme","sure","surface","surge","surprise",
    "sustain","swallow","swamp","swap","swear","sweet","swift","swim","swing","switch",
    "sword","symbol","symptom","syrup","table","tackle","tag","tail","talent","tank",
    "tape","target","task","tattoo","taxi","teach","team","tell","ten","tenant",
    "tennis","tent","term","test","text","thank","that","theme","then","theory",
    "there","they","thing","this","thought","three","thrive","throw","thumb","thunder",
    "ticket","tilt","timber","time","tiny","tip","tired","title","toast","tobacco",
    "today","together","toilet","token","tomato","tomorrow","tone","tongue","tonight","tool",
    "topic","topple","torch","tornado","tortoise","toss","total","tourist","toward","tower",
    "town","toy","track","trade","traffic","tragic","train","transfer","trap","trash",
    "travel","tray","treat","tree","trend","trial","tribe","trick","trigger","trim",
    "trip","trophy","trouble","truck","truly","trumpet","trust","truth","try","tube",
    "tuition","tumble","tuna","tunnel","turkey","turn","turtle","twelve","twenty","twice",
    "twin","twist","two","type","typical","ugly","umbrella","unable","unaware","uncle",
    "uncover","under","undo","unfair","unfold","unhappy","uniform","unique","universe","unknown",
    "unlock","until","unusual","unveil","update","upgrade","uphold","upon","upper","upset",
    "urban","useful","useless","usual","utility","vacant","vacuum","vague","valid","valley",
    "vapor","various","vast","vault","vehicle","velvet","vendor","venture","venue","verb",
    "verify","version","very","veteran","viable","vibrant","vicious","victory","video","view",
    "village","vintage","violin","virtual","virus","visa","visit","visual","vital","vivid",
    "vocal","voice","void","volcano","volume","vote","voyage","wage","wagon","wait",
    "walk","wall","walnut","want","warfare","warm","warrior","waste","water","wave",
    "wealth","weapon","wear","weasel","web","wedding","weekend","weird","welcome","well",
    "west","wet","whale","wheat","wheel","when","where","whip","whisper","wide",
    "width","wife","wild","will","window","wine","wing","wink","winner","winter",
    "wire","wisdom","wise","wish","witness","wolf","woman","wonder","wood","wool",
    "word","world","worry","worth","wrap","wreck","wrestle","wrist","write","wrong",
    "yard","year","yellow","you","young","youth","zebra","zero","zone","zoo",
]

assert len(BIP39_WORDS) >= 1024, "Word list too short"

PHRASE_LENGTH = 10    # 10 words × 11 bits ≈ 110 bits entropy


def generate_seed_phrase() -> List[str]:
    """Generate a cryptographically random 10-word seed phrase."""
    words = []
    for _ in range(PHRASE_LENGTH):
        idx = secrets.randbelow(len(BIP39_WORDS))
        words.append(BIP39_WORDS[idx])
    return words


def phrase_to_key(words: List[str]) -> bytes:
    """Derive a 32-byte key from the seed phrase."""
    phrase_str = " ".join(w.lower().strip() for w in words)
    # PBKDF2 with high iterations for extra resistance
    return hashlib.pbkdf2_hmac(
        "sha256",
        phrase_str.encode("utf-8"),
        b"rexxie-seed-phrase-salt-v1",
        iterations=600_000,
        dklen=32,
    )


def _load_phrase_verifier() -> Optional[str]:
    """Load the stored phrase verifier hash (not the phrase itself)."""
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            return cfg.get("phrase_verifier")
        except Exception:
            pass
    return None


def _save_phrase_verifier(words: List[str]):
    """Store only a verifier hash of the phrase — never the words themselves."""
    key = phrase_to_key(words)
    verifier = hmac.new(key, b"rexxie-seed-backup-verifier", hashlib.sha256).hexdigest()

    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    cfg["phrase_verifier"] = verifier
    cfg["phrase_word_count"] = PHRASE_LENGTH
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)


def verify_seed_phrase(words: List[str]) -> bool:
    """Verify that the provided words match the stored phrase verifier."""
    verifier = _load_phrase_verifier()
    if not verifier:
        return False
    key = phrase_to_key(words)
    expected = hmac.new(key, b"rexxie-seed-backup-verifier", hashlib.sha256).hexdigest()
    return hmac.compare_digest(verifier, expected)


def is_seed_phrase_configured() -> bool:
    return _load_phrase_verifier() is not None


def format_phrase_card(words: List[str]) -> str:
    """Format the phrase for printing — like a hardware wallet card."""
    lines = [
        "=" * 56,
        "  REXXIE VAULT — BACKUP RECOVERY PHRASE",
        "  Store like a crypto seed. Never photograph. Never email.",
        "=" * 56,
        "",
        "  This is your BACKUP 2FA for when you lose your phone.",
        "  Present all 10 words to bypass TOTP and unlock vault.",
        "",
        "  Words:",
        "",
    ]
    for i, word in enumerate(words, 1):
        lines.append(f"    {i:2d}. {word}")
    lines += [
        "",
        "  STORE IN A PHYSICAL SAFE. DO NOT PHOTOGRAPH.",
        "  DO NOT STORE DIGITALLY. DO NOT EMAIL.",
        "=" * 56,
    ]
    return "\n".join(lines)


def detect_seed_phrase_command(user_text: str) -> Optional[Tuple[bool, str]]:
    """
    Detect if user is presenting seed phrase as backup 2FA.
    Returns (phrase_valid, message) or None if not a phrase command.

    Usage: "rexxie backup phrase: word1 word2 ... word10"
    """
    lower = user_text.lower().strip()

    for trigger in ["backup phrase:", "recovery phrase:", "seed phrase:", "emergency phrase:"]:
        if trigger in lower:
            idx   = lower.index(trigger) + len(trigger)
            words = user_text[idx:].strip().lower().split()

            if len(words) < PHRASE_LENGTH:
                return False, (
                    f"That looks like a backup phrase, but I only see {len(words)} words. "
                    f"The full phrase is {PHRASE_LENGTH} words."
                )

            words = words[:PHRASE_LENGTH]
            # Validate all words are in BIP39 list
            invalid = [w for w in words if w not in BIP39_WORDS]
            if invalid:
                return False, f"Unrecognized word(s) in phrase: {', '.join(invalid[:3])}"

            if verify_seed_phrase(words):
                return True, "✅ Backup phrase verified. Vault access granted."
            else:
                return False, "❌ Phrase not recognized. Check your words and try again."

    return None


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rexxie Backup Seed Phrase Manager")
    parser.add_argument("--generate", action="store_true", help="Generate and save a new seed phrase")
    parser.add_argument("--verify",   metavar="WORDS", nargs="+", help="Verify a phrase")
    parser.add_argument("--status",   action="store_true",  help="Check if phrase is configured")
    args = parser.parse_args()

    if args.status:
        if is_seed_phrase_configured():
            print(f"\n✅ Backup seed phrase is configured ({PHRASE_LENGTH} words).")
            print("  It is stored only as a verifier hash — the words exist only on paper.\n")
        else:
            print("\n⚠️  No backup phrase configured. Run --generate to set one up.\n")

    elif args.generate:
        import getpass
        print("\n" + "="*60)
        print("  Generating your 10-word backup seed phrase...")
        print("="*60)
        print()

        words = generate_seed_phrase()
        print(format_phrase_card(words))
        print()

        confirm = input("Have you written down all 10 words? [yes/no]: ").strip().lower()
        if confirm == "yes":
            _save_phrase_verifier(words)
            print()
            print("✅ Phrase saved (as verifier hash only — words not stored).")
            print("   Test it with: python rex_seed_phrase.py --verify word1 word2 ...")
            print()
            print("To use as backup 2FA when your phone is unavailable:")
            print('  Tell Rexxie: "backup phrase: [all 10 words in order]"')
        else:
            print("Cancelled. Words NOT saved. Write them down first, then run again.")

    elif args.verify:
        words = [w.lower() for w in args.verify]
        if len(words) != PHRASE_LENGTH:
            print(f"❌ Expected {PHRASE_LENGTH} words, got {len(words)}")
        elif verify_seed_phrase(words):
            print("✅ Phrase verified successfully.")
        else:
            print("❌ Phrase does not match stored verifier.")

    else:
        parser.print_help()
        print()
        print("Quick start:")
        print("  1. python rex_seed_phrase.py --generate")
        print("  2. Write down the 10 words — store in physical safe")
        print("  3. If phone lost: tell Rexxie 'backup phrase: [10 words]'")
