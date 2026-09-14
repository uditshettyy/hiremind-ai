import json
from app.agents.intake.router import SkillGapRequest

user_payload = {
  "candidate_id": "test-1",
  "job_id": "test-1",
  "resume_text": "UditShetty\nInformation Science & Engineering Student\nMangalore, Karnataka\nEnvelope uditshetty091@gmail.com\nLINKEDIN-IN udit-shetty\nGithub uditshettyy\nSummary\n○A motivated Information Science and Engineering student with strong programming skills in\nPython, C, C++, and Java. Proﬁcient in Power BI with the ability to analyze and visualize\ndata eﬀectively. Passionate about software development, problem-solving, and continuous\nlearning.\nEducation\n2023 –\nPresent\nBachelor of Engineering, Information Science and Engineering, AJ Institute of Engineering\nand Technology, Mangalore\nExpected Graduation: 2027\nTechnical Skills\n○Programming Languages: Python, C, C++,\nJava\n○Tools & Technologies: Power BI\nProjects\n○Blockchain-based Crowdfunding Platform – Developed using decentralized architecture\nand smart contracts.\n○Java-based Tourism and Management System – Implemented core management opera-\ntions such as booking, scheduling, and user data handling.\n○Data Visualizations & Dashboards – Built using Power BI for analytical insights.\nPersonal Details\n○Age: 20 years\n○Hometown: Mangalore, Karnataka",
  "parsed_jd": {
    "title": None,
    "company": "NovaTech Solutions",
    "requirements": [
      {"skill_name": "Python", "category": "programming_language", "required_level": "competent", "priority": 5, "evidence": "Python"},
      {"skill_name": "SQL", "category": "database", "required_level": "competent", "priority": 5, "evidence": "SQL"},
      {"skill_name": "Git", "category": "version_control", "required_level": "competent", "priority": 5, "evidence": "Git"},
      {"skill_name": "REST API", "category": "api", "required_level": "competent", "priority": 5, "evidence": "REST APIs"},
      {"skill_name": "Data Structures and Algorithms", "category": "data_structures_algorithms", "required_level": "novice", "priority": 5, "evidence": "basic data structures and algorithms"},
      {"skill_name": "FastAPI", "category": "framework", "required_level": "novice", "priority": 3, "evidence": "FastAPI or React experience is a plus"},
      {"skill_name": "React", "category": "framework", "required_level": "novice", "priority": 3, "evidence": "FastAPI or React experience is a plus"}
    ],
    "responsibilities": [
      "Develop software applications",
      "Build APIs",
      "Work with databases",
      "Debug issues",
      "Collaborate with the development team"
    ],
    "raw_text": "Software Engineer Intern at NovaTech Solutions. Requirements: Python, SQL, Git, REST APIs, basic data structures and algorithms. Responsibilities: Develop software applications, build APIs, work with databases, debug issues, and collaborate with the development team. FastAPI or React experience is a plus."
  }
}

try:
    obj = SkillGapRequest.model_validate(user_payload)
    print("SUCCESS: Valid payload structure for SkillGapRequest!")
    print("Candidate ID:", obj.candidate_id)
    print("Job ID:", obj.job_id)
    print("Requirements count:", len(obj.parsed_jd.requirements))
except Exception as e:
    print("VALIDATION ERROR:", e)
