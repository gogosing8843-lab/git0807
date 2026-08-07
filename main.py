import datetime
from scraper import scrape_mois, scrape_mss, scrape_moel, save_to_excel

def main():
    print("=== 타기관(행안부, 중기부, 고용부) 사업공고 자동 수집 프로그램 ===")
    
    # 1. 30일 이내 공고 수집
    mois_data = scrape_mois(limit_days=30)
    mss_data = scrape_mss(limit_days=30)
    moel_data = scrape_moel(limit_days=30)
    
    total_count = len(mois_data) + len(mss_data) + len(moel_data)
    print(f"\n총 수집된 공고: {total_count}건")
    print(f"- 행정안전부: {len(mois_data)}건")
    print(f"- 중소벤처기업부: {len(mss_data)}건")
    print(f"- 고용노동부: {len(moel_data)}건")
    
    # 2. 엑셀 파일명 생성 (타기관벤치마킹_YYYYMMDD.xlsx)
    today_str = datetime.date.today().strftime("%Y%m%d")
    output_filename = f"타기관벤치마킹_{today_str}.xlsx"
    
    # 3. 엑셀 저장
    save_to_excel(mois_data, mss_data, moel_data, output_filename)
    print("\n수집 및 엑셀 저장이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    main()
