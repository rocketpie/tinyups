# TinyUPS build system.
# Single source of truth for all design checks, used locally and in CI.

SHELL := /bin/bash

PROJECT ?= hardware/tinyups
SCH     := $(PROJECT).kicad_sch
PCB     := $(PROJECT).kicad_pcb
NAME    := $(notdir $(PROJECT))
OUT     ?= build
REPORTS ?= reports
SIMS    ?= sim/*.cir

KICAD_CLI ?= kicad-cli
PYTHON    ?= /opt/eda/venv/bin/python

# KiCad's global library tables point at ${KICAD9_FOOTPRINT_DIR}. The KiCad GUI
# sets it itself, but headless `kicad-cli` does not, so without this DRC cannot
# resolve the stock footprints and reports ~120 spurious lib_footprint_issues
# warnings. Set it (overridable from the environment) for reproducible checks.
export KICAD9_FOOTPRINT_DIR ?= /usr/share/kicad/footprints
export KICAD9_SYMBOL_DIR    ?= /usr/share/kicad/symbols
export KICAD9_3DMODEL_DIR   ?= /usr/share/kicad/3dmodels

# 3D render camera (override on the command line, e.g. RENDER_ROTATE=-30,0,45)
RENDER_ROTATE ?= -15,0,-5
RENDER_ZOOM   ?= 0.95

.PHONY: all help erc drc netlist bom gerbers drill fab pos step render svg silk sim test power layout mermaid baseline place place-render place-apply check clean

all: help

help: ## Show available targets
	@echo "TinyUPS targets (project: $(PROJECT))"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

# --- helpers ---------------------------------------------------------------
$(OUT) $(REPORTS):
	@mkdir -p $@

define require
	@test -f $(1) || { echo "error: missing $(1)"; exit 1; }
endef

# --- schematic -------------------------------------------------------------
erc: | $(REPORTS) ## Electrical rule check
	$(call require,$(SCH))
	$(KICAD_CLI) sch erc --exit-code-violations --severity-all \
		--output $(REPORTS)/erc.rpt $(SCH)

netlist: | $(OUT) ## Export netlist
	$(call require,$(SCH))
	$(KICAD_CLI) sch export netlist --output $(OUT)/$(NAME).net $(SCH)

bom: | $(OUT) ## Export bill of materials (CSV)
	$(call require,$(SCH))
	$(KICAD_CLI) sch export bom --output $(OUT)/$(NAME)-bom.csv $(SCH)

# --- pcb -------------------------------------------------------------------
drc: | $(REPORTS) ## Design rule check (incl. schematic parity)
	$(call require,$(PCB))
	$(KICAD_CLI) pcb drc --exit-code-violations --severity-all --schematic-parity \
		--output $(REPORTS)/drc.rpt $(PCB)

gerbers: | $(OUT) ## Export Gerber files
	$(call require,$(PCB))
	@mkdir -p $(OUT)/gerbers
	$(KICAD_CLI) pcb export gerbers --output $(OUT)/gerbers/ $(PCB)

drill: | $(OUT) ## Export Excellon drill files
	$(call require,$(PCB))
	@mkdir -p $(OUT)/gerbers
	$(KICAD_CLI) pcb export drill --excellon-units mm --generate-map --map-format gerberx2 \
		--output $(OUT)/gerbers/ $(PCB)

fab: gerbers drill ## Full fabrication package

pos: | $(OUT) ## Export pick&place / position file (CSV)
	$(call require,$(PCB))
	$(KICAD_CLI) pcb export pos --format csv --units mm --side both \
		--output $(OUT)/$(NAME)-pos.csv $(PCB)

step: | $(OUT) ## Export 3D STEP model
	$(call require,$(PCB))
	$(KICAD_CLI) pcb export step --force --output $(OUT)/$(NAME).step $(PCB)

render: | $(OUT) ## Export PCB 3D render (isometric PNG, component bodies)
	$(call require,$(PCB))
	$(KICAD_CLI) pcb render --side top --perspective --quality high \
		--rotate $(RENDER_ROTATE) --zoom $(RENDER_ZOOM) \
		--width 2000 --height 1400 \
		--output $(OUT)/$(NAME).png $(PCB)

svg: | $(OUT) ## Export schematic + PCB SVGs for review
	$(call require,$(SCH))
	$(KICAD_CLI) sch export svg --output $(OUT)/sch-svg $(SCH)
	$(call require,$(PCB))
	@mkdir -p $(OUT)/pcb-svg
	$(KICAD_CLI) pcb export svg --mode-multi \
		--layers F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
		--output $(OUT)/pcb-svg/ $(PCB)

# 2D top view with the power-handling components outlined in RED silkscreen
# (hardware/power_silk.py draws the outlines; this colours them red).
silk: | $(OUT) ## 2D view with red power-silkscreen markers
	$(call require,$(PCB))
	@mkdir -p ~/.config/kicad/9.0/colors
	@cp hardware/themes/tinyups-red.json ~/.config/kicad/9.0/colors/
	$(KICAD_CLI) pcb export svg --mode-single \
		--layers F.Cu,F.Silkscreen,Edge.Cuts --theme tinyups-red \
		--output $(OUT)/$(NAME)-power.svg $(PCB)

# --- power -----------------------------------------------------------------
power: | $(REPORTS) ## Power / ampacity check (design current per net)
	$(call require,$(PCB))
	@set -o pipefail; $(PYTHON) hardware/power_report.py $(PCB) | tee $(REPORTS)/power.rpt

# --- auto-placement PoC (hardware/layout_poc) -------------------------------
# Netlist -> placement graph -> d3-force / dagre / ELK / graphviz -> legalise ->
# SVG+PNG renders + score table.  See hardware/layout_poc/README.md.
LAYOUT_DIR ?= hardware/layout_poc
layout: | $(OUT) ## Auto-placement PoC: run all layout engines + render
	@test -f $(OUT)/$(NAME).net || $(MAKE) --no-print-directory netlist
	cd $(LAYOUT_DIR) && { [ -d node_modules ] || npm install --no-audit --no-fund; }
	$(PYTHON) $(LAYOUT_DIR)/extract.py
	cd $(LAYOUT_DIR) && ./run_all.sh
	$(PYTHON) $(LAYOUT_DIR)/compare.py
	$(PYTHON) $(LAYOUT_DIR)/contact_sheet.py

mermaid: | $(OUT) ## Render the placement graph as a mermaid flowchart (SVG)
	@test -f $(OUT)/$(NAME).net || $(MAKE) --no-print-directory netlist
	@test -d $(LAYOUT_DIR)/node_modules || (cd $(LAYOUT_DIR) && npm install --no-audit --no-fund)
	@test -f $(OUT)/layout/graph.json || $(PYTHON) $(LAYOUT_DIR)/extract.py
	cd $(LAYOUT_DIR) && ./render_mermaid.sh

# --- baseline layout --------------------------------------------------------
# The PoC's conclusion: the graph-derived placement is the new baseline.  This
# materialises the adopted engine's legalised placement as a full KiCad board,
# which is the starting point for the interactive-placement phase.
#   make baseline                      # adopted default (graphviz sfdp)
#   make baseline BASELINE_ENGINE=d3force
BASELINE_ENGINE ?= gv-sfdp
baseline: | $(OUT) ## Materialise the adopted (sfdp) placement as the baseline board
	@test -f $(OUT)/layout/leg-$(BASELINE_ENGINE).json || \
		{ echo "error: run 'make layout' first"; exit 1; }
	$(PYTHON) $(LAYOUT_DIR)/apply.py $(OUT)/layout/leg-$(BASELINE_ENGINE).json \
		$(OUT)/layout/baseline.kicad_pcb

# --- interactive placement (hardware/layout_poc/web) ------------------------
# Browser UI: drag parts around (a dragged part is pinned / fixed for the
# solver), with a live d3-force engine whose parameters are all editable.  The
# server only serves files + a save/apply API; the solver runs in the browser.
# See hardware/layout_poc/web/README.md.
PLACE_PORT ?= 4097
F ?= $(OUT)/layout/interactive-baseline.json
place: | $(OUT) ## Interactive placement UI (http://localhost:4097)
	@test -f $(OUT)/$(NAME).net || $(MAKE) --no-print-directory netlist
	@test -f $(OUT)/layout/graph.json || $(PYTHON) $(LAYOUT_DIR)/extract.py
	@test -d $(LAYOUT_DIR)/node_modules || (cd $(LAYOUT_DIR) && npm install --no-audit --no-fund)
	PORT=$(PLACE_PORT) node $(LAYOUT_DIR)/web/server.mjs

place-render: | $(OUT) ## Render a saved interactive placement (F=<positions.json>)
	$(PYTHON) $(LAYOUT_DIR)/render.py $(F) $(OUT)/layout/interactive.png --label

place-apply: | $(OUT) ## Apply a saved interactive placement to a board + DRC (F=<positions.json>)
	$(PYTHON) $(LAYOUT_DIR)/apply.py $(F) $(OUT)/layout/interactive.kicad_pcb

# --- simulation ------------------------------------------------------------
sim: ## Run all ngspice simulations in sim/
	@shopt -s nullglob; files=($(SIMS)); \
	if [ $${#files[@]} -eq 0 ]; then echo "no simulations in $(SIMS)"; exit 0; fi; \
	for f in "$${files[@]}"; do \
		echo "== ngspice $$f =="; \
		ngspice -b -o "$${f%.cir}.log" "$$f"; \
	done

# --- tests -----------------------------------------------------------------
test: ## Run pytest bring-up / acceptance tests
	$(PYTHON) -m pytest tests/ -v

# --- aggregate -------------------------------------------------------------
check: erc drc netlist bom power ## Run all automated design checks (CI entrypoint)
	@echo "all checks passed"

clean: ## Remove build artifacts
	rm -rf $(OUT) $(REPORTS)
