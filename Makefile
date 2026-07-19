.PHONY: generate test run clean

generate:
	python3 glyphc.py examples/controller.glyph -o demo/src/generated.rs

test: generate
	python3 -m unittest discover -s tests -v

run: generate
	python3 run.py

clean:
	rm -rf __pycache__ glyph/__pycache__ tests/__pycache__ demo/target
