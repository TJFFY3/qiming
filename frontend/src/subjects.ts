/** 学科默认课题；实际检索库 ID 由服务端依据 FastGPT 学科目录解析。 */
export const subjectLessons: Record<string, {chapter: string; edition: string}> = {
  语文: {chapter:"第一单元 青春激扬",edition:"统编版 必修上册"},
  数学: {chapter:"第一章 集合与常用逻辑用语",edition:"人教版 必修第一册"},
  英语: {chapter:"Unit 1 Teenage Life",edition:"人教版 必修第一册"},
  物理: {chapter:"第一章 运动的描述",edition:"人教版 必修第一册"},
  化学: {chapter:"第三节 氧化还原反应",edition:"人教版 必修第一册"},
  生物: {chapter:"第1章 走近细胞",edition:"人教版 必修1"},
  政治: {chapter:"第一课 社会主义从空想到科学、从理论到实践的发展",edition:"人教版 必修1"},
  历史: {chapter:"第一单元 从中华文明起源到秦汉统一多民族封建国家",edition:"统编版 必修上册"},
  地理: {chapter:"第一章 宇宙中的地球",edition:"人教版 必修第一册"},
};
