# Eşi Kızdırmama Oyunu (Don't Make Your Spouse Angry Game)

A humorous Turkish game about navigating marriage scenarios without upsetting your spouse. This comedy game presents exaggerated relationship scenarios based on Turkish culture.

## Game Features

- 20 humorous scenarios about marriage life
- Dynamic scenario generation using OpenAI API
- Each choice affects your path through the game
- Multiple endings based on your performance
- Beautiful web interface with animations

## How to Play

1. Clone this repository
2. Install the required packages: `pip install -r requirements.txt`
3. Create a `.env` file with your OpenAI API key: `OPENAI_API_KEY=your_key_here`
4. Run the game: `python dynamic_game.py`
5. Open your browser to the URL shown in the terminal

## Setup for Deployment

To deploy this game to a public server:

1. Clone the repository
2. Install the required packages: `pip install -r requirements.txt`
3. Set up your environment variables (especially the OpenAI API key)
4. Start the server with gunicorn: `gunicorn dynamic_game:app`

## Technologies Used

- Python
- Flask
- OpenAI API
- HTML/CSS/JavaScript
