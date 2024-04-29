-- Insert fake posts
INSERT INTO post (title, content, subdeaddit, user, created_at)
VALUES
    ('First Post', 'This is the content of the first post.', 'general', 'user1', '2023-06-08 10:00:00'),
    ('Second Post', 'This is the content of the second post.', 'news', 'user2', '2023-06-08 11:30:00'),
    ('Third Post', 'This is the content of the third post.', 'funny', 'user3', '2023-06-08 13:45:00');

-- Insert fake comments for the first post
INSERT INTO comment (post_id, parent_id, content, user, created_at)
VALUES
    (1, NULL, 'Great post!', 'user2', '2023-06-08 10:15:00'),
    (1, 1, 'I agree, thanks for sharing!', 'user3', '2023-06-08 10:30:00'),
    (1, NULL, 'I have a different opinion.', 'user4', '2023-06-08 10:45:00');

-- Insert fake comments for the second post
INSERT INTO comment (post_id, parent_id, content, user, created_at)
VALUES
    (2, NULL, 'Interesting news.', 'user1', '2023-06-08 12:00:00'),
    (2, NULL, 'I have a question about this.', 'user4', '2023-06-08 12:15:00'),
    (2, 5, 'I can help answer that question.', 'user2', '2023-06-08 12:30:00');

-- Insert fake comments for the third post
INSERT INTO comment (post_id, parent_id, content, user, created_at)
VALUES
    (3, NULL, 'Haha, that''s hilarious!', 'user1', '2023-06-08 14:00:00'),
    (3, NULL, 'I don''t find it funny.', 'user5', '2023-06-08 14:15:00');