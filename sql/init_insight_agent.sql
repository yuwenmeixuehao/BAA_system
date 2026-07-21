-- 经营归因分析系统数据库初始化快照
-- 权威来源：backend/migrations；当前版本：20260721_0002
-- 本文件用于全新 MySQL 8.4 数据库，不应独立于 Alembic 手工演进。

CREATE DATABASE IF NOT EXISTS `insight_agent`
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE `insight_agent`;

CREATE TABLE `alembic_version` (
    `version_num` VARCHAR(32) NOT NULL,
    CONSTRAINT `alembic_version_pkc` PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `users` (
    `id` VARCHAR(36) NOT NULL,
    `external_user_id` VARCHAR(255) NOT NULL,
    `username` VARCHAR(100) NULL,
    `email` VARCHAR(320) NULL,
    `display_name` VARCHAR(100) NOT NULL,
    `role` VARCHAR(20) NOT NULL DEFAULT 'user',
    `status` VARCHAR(20) NOT NULL DEFAULT 'active',
    `last_login_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE (`external_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `conversations` (
    `id` VARCHAR(36) NOT NULL,
    `user_id` VARCHAR(36) NOT NULL,
    `title` VARCHAR(200) NOT NULL DEFAULT '新会话',
    `status` VARCHAR(20) NOT NULL DEFAULT 'draft',
    `last_message_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_conversations_user_status_updated`
    ON `conversations` (`user_id`, `status`, `updated_at`);

CREATE TABLE `messages` (
    `id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `task_id` VARCHAR(36) NULL,
    `client_msg_id` VARCHAR(100) NULL,
    `seq_no` INTEGER NOT NULL,
    `role` VARCHAR(20) NOT NULL,
    `message_type` VARCHAR(30) NOT NULL DEFAULT 'text',
    `tool_name` VARCHAR(60) NULL,
    `tool_status` VARCHAR(30) NULL,
    `content` MEDIUMTEXT NULL,
    `content_json` JSON NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `uq_messages_conversation_seq`
        UNIQUE (`conversation_id`, `seq_no`),
    CONSTRAINT `uq_messages_conversation_client_msg`
        UNIQUE (`conversation_id`, `client_msg_id`),
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_messages_task_id` ON `messages` (`task_id`);
CREATE INDEX `ix_messages_conversation_created`
    ON `messages` (`conversation_id`, `created_at`);

CREATE TABLE `attachments` (
    `id` VARCHAR(36) NOT NULL,
    `user_id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `message_id` VARCHAR(36) NULL,
    `file_name` VARCHAR(255) NOT NULL,
    `storage_key` VARCHAR(500) NOT NULL,
    `mime_type` VARCHAR(100) NOT NULL,
    `file_size` BIGINT NOT NULL,
    `sha256` VARCHAR(64) NULL,
    `parse_status` VARCHAR(20) NOT NULL DEFAULT 'pending',
    `parse_error` VARCHAR(1000) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`message_id`) REFERENCES `messages` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_attachments_conversation_created`
    ON `attachments` (`conversation_id`, `created_at`);

CREATE TABLE `analysis_tasks` (
    `id` VARCHAR(36) NOT NULL,
    `user_id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `message_id` VARCHAR(36) NOT NULL,
    `client_msg_id` VARCHAR(100) NOT NULL,
    `task_status` VARCHAR(30) NOT NULL DEFAULT 'queued',
    `current_step` VARCHAR(60) NULL,
    `thread_id` VARCHAR(100) NOT NULL,
    `input_text` TEXT NOT NULL,
    `input_json` JSON NULL,
    `retry_count` INTEGER NOT NULL DEFAULT 0,
    `cancel_requested` BOOL NOT NULL DEFAULT 0,
    `started_at` DATETIME NULL,
    `finished_at` DATETIME NULL,
    `error_code` VARCHAR(60) NULL,
    `error_message` VARCHAR(1000) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `uq_tasks_user_conversation_client_msg`
        UNIQUE (`user_id`, `conversation_id`, `client_msg_id`),
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`message_id`) REFERENCES `messages` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_tasks_conversation_status`
    ON `analysis_tasks` (`conversation_id`, `task_status`);
CREATE INDEX `ix_tasks_user_created`
    ON `analysis_tasks` (`user_id`, `created_at`);

CREATE TABLE `task_events` (
    `id` VARCHAR(36) NOT NULL,
    `task_id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `event_seq` BIGINT NOT NULL,
    `event_type` VARCHAR(40) NOT NULL,
    `payload_json` JSON NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `uq_task_events_task_seq` UNIQUE (`task_id`, `event_seq`),
    FOREIGN KEY (`task_id`) REFERENCES `analysis_tasks` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_task_events_conversation_created`
    ON `task_events` (`conversation_id`, `created_at`);

CREATE TABLE `analysis_results` (
    `id` VARCHAR(36) NOT NULL,
    `task_id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `schema_version` VARCHAR(20) NOT NULL DEFAULT '1.0',
    `problem_definition` JSON NOT NULL,
    `key_metrics_json` JSON NOT NULL,
    `evidence_list_json` JSON NOT NULL,
    `conclusion_text` MEDIUMTEXT NOT NULL,
    `missing_data_text` MEDIUMTEXT NOT NULL,
    `next_action_text` MEDIUMTEXT NOT NULL,
    `result_markdown` MEDIUMTEXT NULL,
    `result_file_path` VARCHAR(500) NULL,
    `report_ir_json` JSON NOT NULL,
    `validation_status` VARCHAR(20) NOT NULL DEFAULT 'pending',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE (`task_id`),
    FOREIGN KEY (`task_id`) REFERENCES `analysis_tasks` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `report_files` (
    `id` VARCHAR(36) NOT NULL,
    `task_id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `file_type` VARCHAR(20) NOT NULL,
    `file_name` VARCHAR(255) NOT NULL,
    `storage_key` VARCHAR(500) NOT NULL,
    `file_size` BIGINT NOT NULL,
    `sha256` VARCHAR(64) NULL,
    `expires_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`task_id`) REFERENCES `analysis_tasks` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_report_files_task_type`
    ON `report_files` (`task_id`, `file_type`);

CREATE TABLE `context_summaries` (
    `id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `start_seq_no` INTEGER NOT NULL,
    `end_seq_no` INTEGER NOT NULL,
    `summary_text` MEDIUMTEXT NOT NULL,
    `summary_version` INTEGER NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_context_summaries_conversation_end`
    ON `context_summaries` (`conversation_id`, `end_seq_no`);

CREATE TABLE `websocket_tokens` (
    `id` VARCHAR(36) NOT NULL,
    `user_id` VARCHAR(36) NOT NULL,
    `conversation_id` VARCHAR(36) NOT NULL,
    `token_hash` VARCHAR(64) NOT NULL,
    `expires_at` DATETIME NOT NULL,
    `consumed_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE (`token_hash`),
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `system_configs` (
    `id` VARCHAR(36) NOT NULL,
    `config_key` VARCHAR(100) NOT NULL,
    `config_value` JSON NOT NULL,
    `config_group` VARCHAR(50) NOT NULL,
    `version` BIGINT NOT NULL DEFAULT 1,
    `updated_by` VARCHAR(36) NULL,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE (`config_key`),
    FOREIGN KEY (`updated_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `task_logs` (
    `id` VARCHAR(36) NOT NULL,
    `task_id` VARCHAR(36) NOT NULL,
    `log_level` VARCHAR(20) NOT NULL,
    `log_type` VARCHAR(30) NOT NULL,
    `log_content` MEDIUMTEXT NOT NULL,
    `trace_id` VARCHAR(100) NULL,
    `duration_ms` BIGINT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`task_id`) REFERENCES `analysis_tasks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_task_logs_task_created`
    ON `task_logs` (`task_id`, `created_at`);
CREATE INDEX `ix_task_logs_trace_created`
    ON `task_logs` (`trace_id`, `created_at`);

CREATE TABLE `audit_logs` (
    `id` VARCHAR(36) NOT NULL,
    `actor_user_id` VARCHAR(36) NULL,
    `action` VARCHAR(100) NOT NULL,
    `resource_type` VARCHAR(60) NOT NULL,
    `resource_id` VARCHAR(100) NULL,
    `detail_json` JSON NULL,
    `ip_address` VARCHAR(64) NULL,
    `trace_id` VARCHAR(100) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX `ix_audit_logs_actor_created`
    ON `audit_logs` (`actor_user_id`, `created_at`);
CREATE INDEX `ix_audit_logs_trace_created`
    ON `audit_logs` (`trace_id`, `created_at`);

CREATE TABLE `data_sources` (
    `id` VARCHAR(36) NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `source_type` VARCHAR(40) NOT NULL,
    `config_json` JSON NOT NULL,
    `secret_ref` VARCHAR(255) NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'disabled',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO `alembic_version` (`version_num`) VALUES ('20260721_0002');
