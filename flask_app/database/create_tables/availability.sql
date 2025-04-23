CREATE TABLE IF NOT EXISTS `availability` (
`event_id`      int(11)      NOT NULL   COMMENT 'the id of the event',
`email`         varchar(100) NOT NULL   COMMENT 'the email of the available person',
`date`          varchar(100) NOT NULL   COMMENT 'the date of availability mm/dd/yy',
`time`          varchar(100) NOT NULL   COMMENT 'the 30-minute time slot this availability starts at hh:mm:ss',
`status`        ENUM('available', 'maybe', 'unavailable') COMMENT 'their availability status',
PRIMARY KEY (`event_id`, `email`, `date`, `time`),
FOREIGN KEY (`event_id`) REFERENCES events(`event_id`),
FOREIGN KEY (`email`) REFERENCES users(`email`),
FOREIGN KEY (`event_id`, `date`) REFERENCES event_dates(`event_id`, `date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT="User availability for events";
