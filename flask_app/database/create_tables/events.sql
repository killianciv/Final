CREATE TABLE IF NOT EXISTS `events` (
`event_id`         int(11)  	   NOT NULL auto_increment  COMMENT 'the id of this event',
`name`             varchar(100)    NOT NULL                 COMMENT 'the name of the event',
`email`            varchar(100)    NOT NULL                 COMMENT 'the email of the creator of the event',
`start_date`       varchar(100)    NOT NULL                 COMMENT 'the first date of the event',
`end_date`         varchar(100)    NOT NULL                 COMMENT 'the last date of the event',
`start_time`       int(5)          NOT NULL                 COMMENT 'the military hour the event starts each day',
`end_time`         int(5)          NOT NULL                 COMMENT 'the military hour the event ends each day',
PRIMARY KEY (`event_id`),
FOREIGN KEY (`email`) REFERENCES users(`email`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="Contains site user information";