INSERT INTO comment (post_id, parent_id, content, upvote_count, user, created_at)
VALUES
    (1, NULL, 'This is the first comment on post 1', 10, 'user1', '2023-05-20 10:00:00'),
    (1, 1, 'This is a reply to the first comment', 5, 'user2', '2023-05-20 11:00:00'),
    (1, NULL, 'This is the second comment on post 1', 8, 'user3', '2023-05-20 12:00:00'),
    (1, 3, 'This is a reply to the second comment', 3, 'user4', '2023-05-20 13:00:00'),
    (1, 1, 'This is another reply to the first comment', 2, 'user5', '2023-05-20 14:00:00');
