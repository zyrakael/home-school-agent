-- 家校沟通 Agent MVP 数据库建表 SQL (MySQL)
-- 运行前请先创建数据库: CREATE DATABASE agent DEFAULT CHARACTER SET utf8mb4;

-- 班级
CREATE TABLE classes (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    name VARCHAR(64) NOT NULL COMMENT '班级名称',
    grade VARCHAR(32) NOT NULL COMMENT '年级'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学生
CREATE TABLE students (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    name VARCHAR(64) NOT NULL COMMENT '学生姓名',
    class_id VARCHAR(32) NOT NULL COMMENT '班级ID',
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态: active / inactive',
    grade VARCHAR(32) NOT NULL COMMENT '年级',
    homework_completed INT NOT NULL DEFAULT 0 COMMENT '已完成作业数',
    homework_total INT NOT NULL DEFAULT 0 COMMENT '作业总数',
    accuracy_avg DECIMAL(5,4) NOT NULL DEFAULT 0 COMMENT '平均正确率 0-1',
    last_active DATE NOT NULL COMMENT '最近活跃日期',
    INDEX idx_students_class (class_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 作业列表
CREATE TABLE homeworks (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    student_id VARCHAR(32) NOT NULL COMMENT '学生ID',
    title VARCHAR(128) NOT NULL COMMENT '作业标题',
    subject VARCHAR(32) NOT NULL COMMENT '学科',
    assigned_at DATE NOT NULL COMMENT '布置日期',
    due_at DATE NOT NULL COMMENT '截止日期',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending / submitted / late / missing',
    accuracy DECIMAL(5,4) DEFAULT NULL COMMENT '正确率 0-1',
    INDEX idx_homeworks_student (student_id),
    INDEX idx_homeworks_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 作业详情
CREATE TABLE homework_details (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    homework_id VARCHAR(32) NOT NULL COMMENT '作业ID',
    wrong_count INT NOT NULL DEFAULT 0 COMMENT '错题数',
    notes VARCHAR(512) DEFAULT '' COMMENT '教师备注',
    UNIQUE KEY uk_homework_detail (homework_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 作业题目
CREATE TABLE homework_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    homework_detail_id VARCHAR(32) NOT NULL COMMENT '作业详情ID',
    question_text VARCHAR(512) NOT NULL COMMENT '题目内容',
    INDEX idx_questions_detail (homework_detail_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 课堂表现
CREATE TABLE lesson_performances (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    student_id VARCHAR(32) NOT NULL COMMENT '学生ID',
    lesson_id VARCHAR(32) NOT NULL COMMENT '课次ID',
    lesson_title VARCHAR(128) NOT NULL DEFAULT '' COMMENT '课程标题',
    attendance VARCHAR(16) NOT NULL DEFAULT 'present' COMMENT '出勤: present / late / absent',
    interaction_score INT DEFAULT NULL COMMENT '互动评分 1-5',
    base_correct_rate DECIMAL(5,4) DEFAULT NULL COMMENT '基础题正确率',
    advanced_correct_rate DECIMAL(5,4) DEFAULT NULL COMMENT '高阶题正确率',
    notes VARCHAR(512) DEFAULT '' COMMENT '课堂备注',
    INDEX idx_lesson_student (student_id),
    INDEX idx_lesson_lesson (lesson_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 错题记录
CREATE TABLE wrong_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(32) NOT NULL COMMENT '学生ID',
    homework_id VARCHAR(32) NOT NULL COMMENT '所属作业ID',
    knowledge_point VARCHAR(128) NOT NULL COMMENT '知识点',
    question_type VARCHAR(32) NOT NULL DEFAULT '' COMMENT '题型',
    reason_tag VARCHAR(64) NOT NULL DEFAULT '' COMMENT '错因标签: 审题 / 计算 / 知识点未掌握 / ...',
    difficulty VARCHAR(16) NOT NULL DEFAULT 'medium' COMMENT '难度: easy / medium / hard',
    is_corrected TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已订正',
    INDEX idx_wq_student (student_id),
    INDEX idx_wq_homework (homework_id),
    INDEX idx_wq_kp (knowledge_point)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
