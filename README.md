# 🦞 OpenClaw Public Skills

A curated collection of OpenClaw skills ready to use.

> Every skill is self-contained and installable with a single command.

---

## 📦 Available Skills

### 🧠 memory-sync

**AI Long-Term Memory Persistence**

Never let your AI forget. Automatically saves conversation messages, detects session resets, and fuses memories into persistent long-term storage.

- **Problem:** AI loses all context when session resets
- **Solution:** Incremental message extraction + AI memory fusion
- **Features:** Session reset detection, version history, rollback support

```bash
# Install
git clone https://github.com/simoddreamy/openclaw-skills-public.git \
  /root/.openclaw/workspace/skills
bash /root/.openclaw/workspace/skills/memory-sync/install.sh
```

➡️ [memory-sync/README.md](memory-sync/README.md)

---

## 📚 Adding New Skills

Add your skill as a subdirectory:

```
openclaw-skills-public/
├── memory-sync/          ← skill #1
├── another-skill/        ← skill #2
├── ...
└── README.md
```

Each skill directory should contain:
- `SKILL.md` — OpenClaw skill definition
- `install.sh` — One-click installer (recommended)
- `scripts/` — Executable scripts
- `references/` — Documentation
- `README.md` — Skill-specific documentation

---

## 🤝 Contributing

PRs welcome! If you have a skill you'd like to share, open a pull request.

---

**License:** MIT
