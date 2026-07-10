# 🌍 Global Agricultural Machinery Lead Generation Platform

An AI-powered B2B lead generation platform designed for agricultural machinery exporters.

This project automatically discovers global procurement opportunities, extracts customer contact information, analyzes demand using AI, generates personalized sales emails, and supports automated outreach.

---

# 项目简介

全球农机外贸 AI 获客平台。

该项目旨在帮助农机及配件出口企业自动发现海外采购需求，采集客户信息，识别采购意向，并自动生成开发信，提高外贸开发效率。

---

# Features

## 🔍 Demand Discovery

- Google Custom Search API 搜索全球公开采购需求
- 自动发现论坛、招标、采购网站
- 支持自定义关键词搜索
- 自动更新需求数据

---

## 🤖 AI Demand Analysis

- AI 自动识别采购需求
- 提取品牌（Kubota、Yanmar、John Deere 等）
- 提取机型
- 提取零件名称
- 判断采购意向等级
- 去除重复需求

---

## 👥 Customer Information Extraction

自动提取客户信息：

- Company Name
- Website
- Country
- Contact Email
- Product
- Demand Description

支持保存为 JSON。

---

## 📧 AI Email Generation

根据客户需求自动生成英文开发信。

支持：

- 个性化内容
- 产品推荐
- 商务语气
- 自动插入公司信息

---

## 📨 Email Outreach

支持：

- SMTP 邮件发送
- 批量发送开发信
- 邮件日志
- 发送状态记录

---

## ⚙ Automation

- 自动执行搜索任务
- 自动更新需求数据库
- 自动生成开发信
- 自动发送邮件
- 日志管理

---

# Project Structure

```
.
├── demo/
│   ├── demo.py
│   ├── email_sender.py
│   ├── website_email_scraper.py
│   ├── server.py
│   ├── update_emails.py
│   ├── scraper_more.py
│   └── ...
│
├── .cursor/
├── README.md
├── requirements.txt
└── .gitignore
```

---

# Demo

`demo/` 文件夹提供独立示例程序。

包括：

- Google Search
- Website Scraper
- Email Scraper
- AI Demand Extraction
- Email Generator
- Bulk Email Sender

这些 Demo 可以单独运行，也可以作为整个系统的组成部分。

---

# Workflow

```
Google Search

↓

Collect Procurement Information

↓

AI Demand Analysis

↓

Extract Customer Information

↓

Generate Sales Email

↓

Send Email

↓

Save Logs
```

---

# Tech Stack

- Python
- Flask
- Google Custom Search API
- OpenAI API
- JSON
- SMTP
- Git
- Cursor AI

---

# Application Scenarios

适用于：

- Agricultural Machinery
- Tractor Parts
- Construction Machinery
- Heavy Equipment
- Industrial Parts
- B2B Export

---

# Future Roadmap

计划增加：

- CRM Integration
- LinkedIn Lead Generation
- WhatsApp Automation
- Dashboard
- PostgreSQL Database
- Multi-language Email Generation
- Customer Scoring
- AI Sales Assistant

---

# License

MIT License

---

# Author

**Mona Wang**

Business Development | AI Automation | Agricultural Machinery Export

GitHub:

https://github.com/meokokawaii-droid
