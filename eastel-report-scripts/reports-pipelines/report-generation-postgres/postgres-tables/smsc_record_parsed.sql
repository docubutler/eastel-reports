/*
SQLyog Community v13.3.0 (64 bit)
MySQL - 8.0.43 : Database - eastel
*********************************************************************
*/

/*!40101 SET NAMES utf8 */;

/*!40101 SET SQL_MODE=''*/;

/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
CREATE DATABASE /*!32312 IF NOT EXISTS*/`eastel` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `eastel`;

/*Table structure for table `smsc_record_parsed` */

DROP TABLE IF EXISTS `smsc_record_parsed`;

CREATE TABLE `smsc_record_parsed` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `raw_id` bigint DEFAULT NULL,
  `delivery_date` datetime DEFAULT NULL,
  `addr_src_digits` varchar(32) DEFAULT NULL,
  `addr_src_ton` int DEFAULT NULL,
  `addr_src_npi` int DEFAULT NULL,
  `addr_dst_digits` varchar(32) DEFAULT NULL,
  `addr_dst_ton` int DEFAULT NULL,
  `addr_dst_npi` int DEFAULT NULL,
  `message_delivery_status` varchar(32) DEFAULT NULL,
  `origination_type` varchar(32) DEFAULT NULL,
  `message_type` varchar(16) DEFAULT NULL,
  `orig_system_id` varchar(64) DEFAULT NULL,
  `message_id` varchar(64) DEFAULT NULL,
  `dvl_message_id` varchar(64) DEFAULT NULL,
  `receipt_local_message_id` varchar(64) DEFAULT NULL,
  `nnn_digits` varchar(32) DEFAULT NULL,
  `imsi` varchar(32) DEFAULT NULL,
  `corr_id` varchar(64) DEFAULT NULL,
  `originator_sccp_address` varchar(64) DEFAULT NULL,
  `mt_service_center_address` varchar(64) DEFAULT NULL,
  `orig_network_id` int DEFAULT NULL,
  `network_id` int DEFAULT NULL,
  `mproc_notes` varchar(255) DEFAULT NULL,
  `msg_parts` int DEFAULT NULL,
  `char_numbers` int DEFAULT NULL,
  `processing_time` int DEFAULT NULL,
  `delivery_delay` int DEFAULT NULL,
  `schedule_delivery_delay` int DEFAULT NULL,
  `delivery_count` int DEFAULT NULL,
  `sms_text` varchar(255) DEFAULT NULL,
  `reason_for_failure` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2441749 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
