# Wayfinder: A Multimodal Browsing Agent for Real-World Web Tasks

## Setup

```bash
python3.12 -m venv env
source env/bin/activate
pip install -r requirements.txt
playwright install
```

Create a `.env` file and add your OPENAI_API_KEY:

```
OPENAI_API_KEY=your_openai_api_key
```

## Usage

```bash
python3 main.py
```

## WebVoyager Benchmark

```
cd eval/webvoyager
python3 run_webvoyager_benchmark.py --output-dir <output_dir>
```
