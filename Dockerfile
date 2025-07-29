# Use Python 3.12 base image
FROM python:3.12-slim

# Set working directory inside container
WORKDIR /app

# Copy only necessary files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Command to run your bot
CMD ["python", "main.py"]
