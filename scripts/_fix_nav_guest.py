"""Fix navigation to distinguish guests from real users."""

with open("templates/base.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

targets = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped == "{% if current_user.is_authenticated %}":
        context_after = "".join(lines[i+1:i+4]) if i+4 < len(lines) else ""
        if "profile" in context_after or "logout" in context_after or "Profil" in context_after:
            targets.append(i)
            print(f"  Line {i+1}: {stripped}")

print(f"\nFound {len(targets)} navigation auth checks to fix")

for i in targets:
    old_line = lines[i]
    new_line = old_line.replace(
        "{% if current_user.is_authenticated %}",
        "{% if current_user.is_authenticated and not current_user.is_guest %}"
    )
    lines[i] = new_line

with open("templates/base.html", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Done! base.html updated.")
