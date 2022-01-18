/*
 Navicat Premium Data Transfer

 Source Server         : kotorilocal
 Source Server Type    : MySQL
 Source Server Version : 50726
 Source Host           : 192.168.0.101:3306
 Source Schema         : kotori

 Target Server Type    : MySQL
 Target Server Version : 50726
 File Encoding         : 65001

 Date: 08/03/2021 16:49:52
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for aria2
-- ----------------------------
DROP TABLE IF EXISTS `aria2`;
CREATE TABLE `aria2`  (
  `mid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `uid` int(11) NULL DEFAULT NULL,
  `gid` int(11) NULL DEFAULT NULL,
  `sid` int(11) NULL DEFAULT NULL,
  `typeid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  PRIMARY KEY (`mid`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
