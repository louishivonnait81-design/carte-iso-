# MicroMacro Castres — pipeline carte isometrique
# Variables surchargeables : make render ROWS=4 COLS=6

PY      ?= python3
ROWS    ?= 4
COLS    ?= 7
TILE    ?= 60
PX      ?= 2048
CENTER  ?= 43.60482 2.24177
ELEV    ?= 45
TILES   ?= tiles
STYLED  ?= styled
QA      ?= qa_out
OUT     ?= out
BUDGET  ?= 5

.PHONY: help install test check density blend notes planche render render-test next status ref02 stylize stylize-dry qa seam assemble all clean

help:
	@echo "make install       installe les dependances Python"
	@echo "make test          lance les tests (sans Blender ni reseau)"
	@echo "make blend         construit assets/castres.blend depuis assets/castres.osm"
	@echo "make render        rend la grille $(ROWS)x$(COLS) depuis assets/castres.blend"
	@echo "make render-test   rend seulement 1x2 tuiles (verification rapide)"
	@echo "make planche      planche-contact des tuiles, pour relire les donnees"
	@echo "make notes         extrait les lieux de chaque tuile depuis l'OSM"
	@echo "make next          MODE MANUEL : prepare la prochaine tuile a coller dans Gemini"
	@echo "make status        MODE MANUEL : avancement de la grille"
	@echo "make ref02         genere les propositions de REF_02_castres.png (API)"
	@echo "make stylize-dry   ecrit les prompts sans appeler l'API"
	@echo "make stylize       habille les tuiles (plafond $(BUDGET) EUR)"
	@echo "make qa            rapport de qualite dans $(QA)/report.html"
	@echo "make density       verifie que les references restent blanches a la reduction"
	@echo "make seam          apercu du raccord entre tile_0_0 et tile_0_1"
	@echo "make assemble      mosaique PNG + SVG dans $(OUT)/"
	@echo "make clean         efface les sorties (garde assets/)"

install:
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest tests/ -q

check:
	$(PY) -m pyflakes render.py stylize.py qa.py assemble.py scripts/*.py

density:
	$(PY) scripts/ink_density.py assets/REF_01_style.png assets/REF_02_castres.png

OSM     ?= assets/castres.osm
export LIBGL_ALWAYS_SOFTWARE ?= 1

blend:
	$(PY) scripts/osm_to_blend.py $(OSM) --out assets/castres.blend

render:
	$(PY) render.py --rows $(ROWS) --cols $(COLS) --tile $(TILE) --px $(PX) \
		--center-latlon $(CENTER) --elevation $(ELEV) --out $(TILES)/

render-test:
	$(PY) render.py --rows 1 --cols 2 --tile $(TILE) --px $(PX) \
		--center-latlon $(CENTER) --elevation $(ELEV) --out $(TILES)/

planche:
	$(PY) scripts/contact_sheet.py --tiles $(TILES) --source sem
	$(PY) scripts/contact_sheet.py --tiles $(TILES) --source lines

notes:
	$(PY) scripts/tile_notes.py --tiles $(TILES) --osm $(OSM)

next:
	$(PY) manual.py --tiles $(TILES) --styled $(STYLED) next

status:
	$(PY) manual.py --tiles $(TILES) --styled $(STYLED) status

ref02:
	$(PY) scripts/gen_ref.py --variants 2 --budget-eur $(BUDGET)

stylize-dry:
	$(PY) stylize.py --tiles $(TILES) --out $(STYLED) --dry-run

stylize:
	$(PY) stylize.py --tiles $(TILES) --out $(STYLED) --budget-eur $(BUDGET)

qa:
	$(PY) qa.py --tiles $(TILES) --styled $(STYLED) --out $(QA)

seam:
	$(PY) scripts/seam_preview.py --styled $(STYLED) --pair tile_0_0 tile_0_1 \
		--out $(QA)/seam_0_0-0_1.png

assemble:
	$(PY) assemble.py --tiles $(TILES) --styled $(STYLED) --out $(OUT)

all: render stylize qa assemble

clean:
	rm -rf manual $(STYLED) $(QA) $(OUT) $(TILES)/*.png $(TILES)/index.json
