CREATE TABLE IF NOT EXISTS `event_dates` (
`event_id`         int(11)  	   NOT NULL                 COMMENT 'the id of this event',
`date`             varchar(100)    NOT NULL                 COMMENT 'the date of one day of the event',
PRIMARY KEY (`event_id`, `date`),
FOREIGN KEY (`event_id`) REFERENCES events(`event_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="Contains site user information";