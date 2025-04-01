# Deploying to Render

This guide explains how to deploy "Eşi Kızdırmama Oyunu" to Render.

## Prerequisites

1. A GitHub account
2. A Render account connected to your GitHub
3. An OpenAI API key (for scenario generation)

## Steps to Deploy

1. Push your code to a GitHub repository:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/yourusername/esi-kizdirmama-oyunu.git
git push -u origin main
```

2. Go to [Render Dashboard](https://dashboard.render.com/)

3. Click "New" and select "Blueprint"

4. Connect your GitHub repository

5. Render will detect the `render.yaml` file and set up your services:
   - A web service for the game
   - A PostgreSQL database

6. Set your environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `DATABASE_URL`: This should be automatically set from the connected database

7. Click "Apply" and wait for the deployment to complete

## Troubleshooting

- If the database doesn't connect, check the environment variables in the Render dashboard
- Make sure the OpenAI API key is correctly set
- Check the logs in the Render dashboard for any errors

## Local Development

For local development, create a `.env` file with:

```
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=sqlite:///game_data.db
```

Then run:

```bash
pip install -r requirements.txt
python dynamic_game.py
``` 