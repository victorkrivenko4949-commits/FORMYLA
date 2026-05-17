import io, sys, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
db = sqlite3.connect("instance/formyla.db")
c = db.cursor()
c.execute(
    "SELECT id, status
