.PHONY: dev install enrich enrich-all

install:
	@npm install

dev:
	@npm run dev

enrich:
	@npm run dev -- enrich $(ID)

enrich-all:
	@npm run dev -- enrich-all

