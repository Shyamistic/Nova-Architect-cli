"""
Nova Architect — Pre-built Architecture Templates
Six click-to-build starting points covering the most common serverless patterns.
"""

TEMPLATES = [
    {
        "id": "photo_sharing",
        "label": "Photo Sharing App",
        "icon": "📸",
        "tags": ["S3", "Lambda", "DynamoDB", "API Gateway"],
        "description": "Upload photos, resize, store, retrieve",
        "prompt": (
            "A photo sharing app with image upload, automatic thumbnail generation, "
            "DynamoDB metadata storage, and a REST API with presigned S3 URLs"
        ),
    },
    {
        "id": "realtime_chat",
        "label": "Real-time Chat",
        "icon": "💬",
        "tags": ["WebSocket API", "DynamoDB", "Lambda"],
        "description": "WebSocket connections, message history, user rooms",
        "prompt": (
            "A real-time chat application with WebSocket API Gateway, Lambda message handler, "
            "DynamoDB for message history and user connections, with room-based architecture"
        ),
    },
    {
        "id": "ecommerce",
        "label": "E-Commerce API",
        "icon": "🛒",
        "tags": ["API Gateway", "Lambda", "DynamoDB", "S3", "Cognito"],
        "description": "Products, cart, orders, authentication",
        "prompt": (
            "A serverless e-commerce backend with product catalog, shopping cart, order management, "
            "Cognito user authentication, and REST API"
        ),
    },
    {
        "id": "data_pipeline",
        "label": "Data Pipeline",
        "icon": "🔄",
        "tags": ["S3", "Lambda", "SQS", "DynamoDB"],
        "description": "Ingest, process, store data at scale",
        "prompt": (
            "A serverless data pipeline that ingests files to S3, triggers Lambda via SQS queue "
            "for processing, stores results in DynamoDB with dead-letter queue for failures"
        ),
    },
    {
        "id": "auth_api",
        "label": "Auth + REST API",
        "icon": "🔐",
        "tags": ["Cognito", "API Gateway", "Lambda", "DynamoDB"],
        "description": "JWT auth, protected routes, user management",
        "prompt": (
            "A REST API with Cognito JWT authentication, protected Lambda endpoints, "
            "DynamoDB user profiles, and API Gateway with Cognito authorizer"
        ),
    },
    {
        "id": "notifications",
        "label": "Notification System",
        "icon": "🔔",
        "tags": ["SNS", "SQS", "Lambda", "DynamoDB"],
        "description": "Multi-channel notifications with queue buffering",
        "prompt": (
            "A notification system with SNS for fan-out, SQS queues for email/SMS/push channels, "
            "Lambda processors per channel, and DynamoDB for notification history and user preferences"
        ),
    },
]
