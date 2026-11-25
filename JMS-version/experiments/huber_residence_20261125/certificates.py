from shared_source import load_shared
load_shared(globals())
base_publish=publish


def publish():
    base_publish()
    cert=OUT/"frontier/certificate.json"
    if not cert.exists():
        return
    f=read(cert)
    combined=OUT/"reuse/additional_certificates.json"
    archive=read(combined)
    for row in archive["free_witnesses"]:
        row.update(conditional_C_lower=None,conditional_C_exact=None,conditional_certificate=None,
                   conditional_certificate_sha256=None)
        if row["n"]!=8:
            continue
        if row["H"]==3 and f.get("H3_complete_frontier"):
            c,b=f["short_end"]
            assert abs(b-row["secondary"])<EPS and abs(c-row["cmax"])<EPS
        elif row["H"]==10 and (a:=f.get("H10_attainment")) and a["lower"]==a["upper"]:
            c=a["lower"]
            detail=OUT/"frontier/H10_attainment_hardware_610/result.json"
            assert read(detail)["lower_C"]==c and sha(detail)==a["lower_source_sha256"]
            assert a["witness"]["exact_native_rows"]>0 and abs(c-row["cmax"])<EPS
        else:
            continue
        row.update(conditional_C_lower=c,conditional_C_exact=True,conditional_certificate=str(cert.relative_to(JMS)),
                   conditional_certificate_sha256=sha(cert))
    rows=archive["free_witnesses"]
    export_csv(OUT/"free_B_shortest_verified.csv",list(rows[0]),rows)
    write(combined,archive)

if __name__=="__main__":
    publish()
