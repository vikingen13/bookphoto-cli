BREW_PREFIX := $(shell brew --prefix 2>/dev/null)
ZSH_COMP_DIR := $(BREW_PREFIX)/share/zsh/site-functions

.PHONY: install uninstall test

install:
	uv tool install . --force
	@mkdir -p "$(ZSH_COMP_DIR)"
	cp completions/_gallery "$(ZSH_COMP_DIR)/_gallery"
	@rm -f ~/.zcompdump*
	@echo ""
	@echo "OK. Completion zsh installee dans $(ZSH_COMP_DIR)."
	@echo "Ouvre un NOUVEAU terminal, puis : gallery <TAB>  /  gallery add mon-album ../<TAB>"

uninstall:
	-uv tool uninstall bookphoto
	rm -f "$(ZSH_COMP_DIR)/_gallery"

test:
	uv run pytest -q
