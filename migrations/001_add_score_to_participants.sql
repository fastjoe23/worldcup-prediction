-- Add score column to participants table if it doesn't exist
ALTER TABLE participants
ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0;
