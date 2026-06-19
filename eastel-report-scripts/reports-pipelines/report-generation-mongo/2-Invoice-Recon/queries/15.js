/*
Query 15: Domestic A2P SMS.

Output columns:
- service_type
- charge_type
- sms_type
- sms_count

Equivalent PostgreSQL:

WITH params AS (
    SELECT
        DATE('2026-04-01') AS report_start_date,
        DATE('2026-05-01') AS report_end_date
)
SELECT
    'SMS' AS service_type,
    CASE
        WHEN (t.addr_src_digits LIKE '2%' OR t.addr_src_digits = '601170337777')
            THEN 'Non-Profit A2P SMS MT Bundled'
        WHEN (t.addr_src_digits LIKE '6%' AND t.addr_src_digits <> '601170337777')
            THEN 'Commercial A2P SMS MT'
    END AS charge_type,
    CASE
        WHEN (t.addr_src_digits LIKE '2%' OR t.addr_src_digits = '601170337777')
            THEN 'Non Profit A2P (22200,22288,22200EASTEL,601170337777)'
        WHEN (t.addr_src_digits LIKE '6%' AND t.addr_src_digits <> '601170337777')
            THEN 'Commercial A2P'
    END AS sms_type,
    COUNT(*) AS sms_count
FROM eastel.smsc_record_parsed t
JOIN params p
WHERE t.message_type = 'message'
  AND t.origination_type = 'SMPP'
  AND t.message_delivery_status IN ('success', 'success_esme')
  AND (
      t.addr_src_digits LIKE '2%'
      OR t.addr_src_digits = '601170337777'
      OR t.addr_src_digits LIKE '6%'
  )
  AND t.delivery_date >= p.report_start_date
  AND t.delivery_date < DATE_ADD(p.report_end_date, INTERVAL 1 DAY)
GROUP BY charge_type, sms_type
ORDER BY charge_type, sms_type;
*/

db.{{smsc_cdr}}.aggregate([
  {
    $match: {
      delivery_date: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      message_type: "message",
      origination_type: "SMPP",
      message_delivery_status: { $in: ["success", "success_esme"] },
      $or: [
        {
          addr_src_digits: {
            $regex: "^2"
          }
        },
        {
          addr_src_digits: "601170337777"
        },
        {
          addr_src_digits: {
            $regex: "^6"
          }
        }
      ]
    }
  },
  {
    $addFields: {
      charge_type: {
        $switch: {
          branches: [
            {
              case: {
                $or: [
                  {
                    $regexMatch: {
                      input: { $ifNull: ["$addr_src_digits", ""] },
                      regex: "^2"
                    }
                  },
                  {
                    $eq: ["$addr_src_digits", "601170337777"]
                  }
                ]
              },
              then: "Non-Profit A2P SMS MT Bundled"
            },
            {
              case: {
                $and: [
                  {
                    $regexMatch: {
                      input: { $ifNull: ["$addr_src_digits", ""] },
                      regex: "^6"
                    }
                  },
                  {
                    $ne: ["$addr_src_digits", "601170337777"]
                  }
                ]
              },
              then: "Commercial A2P SMS MT"
            }
          ],
          default: null
        }
      },
      sms_type: {
        $switch: {
          branches: [
            {
              case: {
                $or: [
                  {
                    $regexMatch: {
                      input: { $ifNull: ["$addr_src_digits", ""] },
                      regex: "^2"
                    }
                  },
                  {
                    $eq: ["$addr_src_digits", "601170337777"]
                  }
                ]
              },
              then: "Non Profit A2P (22200,22288,22200EASTEL,601170337777)"
            },
            {
              case: {
                $and: [
                  {
                    $regexMatch: {
                      input: { $ifNull: ["$addr_src_digits", ""] },
                      regex: "^6"
                    }
                  },
                  {
                    $ne: ["$addr_src_digits", "601170337777"]
                  }
                ]
              },
              then: "Commercial A2P"
            }
          ],
          default: null
        }
      }
    }
  },
  {
    $match: {
      charge_type: { $ne: null }
    }
  },
  {
    $group: {
      _id: {
        charge_type: "$charge_type",
        sms_type: "$sms_type"
      },
      sms_count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "SMS" },
      charge_type: "$_id.charge_type",
      sms_type: "$_id.sms_type",
      sms_count: 1,
      sort_order: {
        $cond: [
          { $eq: ["$_id.charge_type", "Commercial A2P SMS MT"] },
          1,
          2
        ]
      }
    }
  },
  {
    $sort: {
      sort_order: 1,
      sms_type: 1
    }
  },
  {
    $project: {
      sort_order: 0
    }
  }
]);
