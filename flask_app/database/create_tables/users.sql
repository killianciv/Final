CREATE TABLE IF NOT EXISTS `users` (
`user_id`         int(11)  	   NOT NULL auto_increment	  COMMENT 'the id of this user',
`email`           varchar(100) NOT NULL UNIQUE            COMMENT 'the decrypted email',
`password`        varchar(256) NOT NULL                   COMMENT 'the encrypted password',
`role`            varchar(10)  NOT NULL                   COMMENT 'the role of the user; options include: owner and user',
PRIMARY KEY (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="Contains site user information";