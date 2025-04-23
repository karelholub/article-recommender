from flask import Flask, render_template, jsonify, request, abort
from recommend import RecommenderFactory
import json
from pathlib import Path
import logging
from config.logging_config import setup_logging
import traceback
from datetime import datetime

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize recommender
try:
    recommender = RecommenderFactory.create_recommender(
        "advanced",
        diversity_weight=0.3,
        time_decay_days=30,
        cluster_weight=0.2
    )
    logger.info("Recommender initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize recommender: {str(e)}")
    logger.error(traceback.format_exc())
    recommender = None

@app.before_request
def before_request():
    """Validate request before processing"""
    if request.is_json:
        try:
            request.get_json()
        except Exception as e:
            logger.error(f"Invalid JSON in request: {str(e)}")
            abort(400, description="Invalid JSON format")
    
    # Log request details
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def after_request(response):
    """Add security headers and handle CORS"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/articles')
def get_articles():
    """Get all articles with their metadata"""
    if not recommender:
        logger.error("Recommender not initialized")
        return jsonify({'error': 'Recommender not initialized'}), 500
        
    try:
        articles = []
        for article_id, data in recommender.article_vectors.items():
            # Skip articles without proper metadata
            if not data.get('metadata') or not data['metadata'].get('title'):
                logger.warning(f"Skipping article {article_id} due to missing metadata")
                continue
                
            articles.append({
                'article_id': article_id,
                'title': data['metadata']['title'],
                'content': data['metadata'].get('content', ''),
                'metadata': data['metadata']
            })
            
        if not articles:
            logger.warning("No valid articles found")
            return jsonify([])
            
        logger.info(f"Returning {len(articles)} articles")
        return jsonify(articles)
    except Exception as e:
        logger.error(f"Error getting articles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/similar/<article_id>')
def get_similar_articles(article_id):
    """Get similar articles for a given article"""
    if not recommender:
        logger.error("Recommender not initialized")
        return jsonify({'error': 'Recommender not initialized'}), 500
        
    try:
        # Get recommendations for the article
        similar_articles = recommender.recommend_for_user(
            "demo_user",
            recommender.article_vectors,
            [article_id],  # Use the article as the user's reading history
            top_n=5
        )
        
        # Add content to the response
        for article in similar_articles:
            article_id = article['article_id']
            if article_id in recommender.article_vectors:
                article['content'] = recommender.article_vectors[article_id]['metadata'].get('content', '')
        
        return jsonify(similar_articles)
    except Exception as e:
        logger.error(f"Error getting similar articles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """Get statistics about articles including cluster distribution and freshness"""
    if not recommender:
        logger.error("Recommender not initialized")
        return jsonify({'error': 'Recommender not initialized'}), 500
        
    try:
        # Get cluster distribution
        cluster_counts = {}
        for article_id, data in recommender.article_vectors.items():
            cluster = data.get('cluster', -1)
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        
        # Get freshness distribution
        freshness_counts = {
            'today': 0,
            'this_week': 0,
            'this_month': 0,
            'older': 0
        }
        
        for article_id, data in recommender.article_vectors.items():
            try:
                scraped_at = datetime.strptime(
                    data['metadata']['scraped_at'],
                    '%Y-%m-%d %H:%M:%S'
                )
                days_old = (datetime.now() - scraped_at).days
                
                if days_old == 0:
                    freshness_counts['today'] += 1
                elif days_old <= 7:
                    freshness_counts['this_week'] += 1
                elif days_old <= 30:
                    freshness_counts['this_month'] += 1
                else:
                    freshness_counts['older'] += 1
            except (KeyError, ValueError):
                freshness_counts['older'] += 1
        
        # Get top topics for each cluster
        cluster_topics = {}
        for article_id, data in recommender.article_vectors.items():
            cluster = data.get('cluster', -1)
            if cluster not in cluster_topics:
                cluster_topics[cluster] = []
            
            # Add article title to cluster topics
            if 'metadata' in data and 'title' in data['metadata']:
                cluster_topics[cluster].append(data['metadata']['title'])
        
        # Get most common words in each cluster's titles
        for cluster in cluster_topics:
            titles = cluster_topics[cluster]
            if titles:
                # Take first 3 titles as representative
                cluster_topics[cluster] = titles[:3]
        
        return jsonify({
            'total_articles': len(recommender.article_vectors),
            'cluster_distribution': cluster_counts,
            'freshness_distribution': freshness_counts,
            'cluster_topics': cluster_topics
        })
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.errorhandler(400)
def bad_request_error(error):
    return jsonify({'error': 'Bad request'}), 400

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 