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

.PHONY: all help erc drc netlist bom gerbers drill fab pos step render svg sim test check clean

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

render: | $(OUT) ## Export PCB render (PNG)
	$(call require,$(PCB))
	$(KICAD_CLI) pcb render --output $(OUT)/$(NAME).png $(PCB)

svg: | $(OUT) ## Export schematic + PCB SVGs for review
	$(call require,$(SCH))
	$(KICAD_CLI) sch export svg --output $(OUT)/sch-svg $(SCH)
	$(call require,$(PCB))
	@mkdir -p $(OUT)/pcb-svg
	$(KICAD_CLI) pcb export svg --mode-multi \
		--layers F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
		--output $(OUT)/pcb-svg/ $(PCB)

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
check: erc drc netlist bom ## Run all automated design checks (CI entrypoint)
	@echo "all checks passed"

clean: ## Remove build artifacts
	rm -rf $(OUT) $(REPORTS)
