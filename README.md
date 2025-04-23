# Article Recommendation System

A Flask-based article recommendation system that uses advanced natural language processing to provide personalized article recommendations.

## Features

- Article scraping and processing
- Multilingual text embedding using Hugging Face's MPNet model
- Advanced recommendation algorithm with:
  - Content-based similarity
  - Diversity optimization
  - Time decay
  - Semantic clustering
- RESTful API endpoints
- User profile management

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd <repo-name>
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the Flask application:
```bash
python app.py
```

The server will start on `http://localhost:5001`

## API Endpoints

- `GET /`: Main page
- `GET /api/articles`: Get all articles
- `GET /api/similar/<article_id>`: Get similar articles
- `GET /api/stats`: Get system statistics

## Project Structure

- `app.py`: Main Flask application
- `recommend.py`: Recommendation system implementation
- `embed.py`: Text embedding and processing
- `scrape.py`: Article scraping functionality
- `config/`: Configuration files
- `templates/`: HTML templates
- `static/`: Static files
- `tests/`: Test files

## Development

- Run tests: `pytest`
- Format code: `black .`
- Lint code: `flake8`

## License

[Your chosen license] 