CREATE TABLE IF NOT EXISTS `invitees` (
`event_id`      INT(11)                 NOT NULL                 COMMENT 'the event id',
`email`         VARCHAR(100)            NOT NULL                 COMMENT 'the email of the invitee. Not necessarily a user',
PRIMARY KEY (`event_id`, `email`),
FOREIGN KEY (`event_id`) REFERENCES events(`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT="Links invitee emails to events, with optional user ID";
