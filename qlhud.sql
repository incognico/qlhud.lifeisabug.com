CREATE TABLE `huds` (
     `id` int(11) NOT NULL AUTO_INCREMENT,
     `author` varchar(31) NOT NULL,
     `description` varchar(2222),
     `ip` varchar(46) NOT NULL,
     `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
     `uniqid` varchar(8) NOT NULL,
     `imgy` int(4) NOT NULL,
     `downloads` int(11) NOT NULL DEFAULT '0',
     `clicks` int(11) NOT NULL DEFAULT '0',
     PRIMARY KEY (`id`),
     UNIQUE KEY `uniqid` (`uniqid`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE TABLE `sessions` (
     `ip` varchar(46) NOT NULL,
     `uniqid` varchar(8) NOT NULL,
     `type` enum('clicks','downloads') NOT NULL,
) ENGINE=MyISAM DEFAULT CHARSET=utf8;

CREATE EVENT clear_sessions
   ON SCHEDULE EVERY 30 MINUTE
   COMMENT 'Clears out sessions table every 30 min.'
   DO
      DELETE FROM qlhud.sessions;
