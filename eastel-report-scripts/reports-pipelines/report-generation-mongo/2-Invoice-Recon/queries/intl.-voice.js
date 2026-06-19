/*
Query 12: International voice calls by destination country.

Equivalent PostgreSQL query:

SELECT
    'Voice' AS service_type,
    'Voice MO' AS charge_type,
    COALESCE(cc.country, 'UNMAPPED') AS country,
    COUNT(*) AS call_count,
    ROUND(SUM(COALESCE(t.act_usage_unit, 0)) / 60.0, 2) AS mou_mins
FROM iot_portal_tb_usage_log t
LEFT JOIN LATERAL (
    SELECT c.country
    FROM country_code c
    WHERE TRIM(t.opposite_number::text) LIKE c.country_code || '%'
    ORDER BY LENGTH(c.country_code) DESC
    LIMIT 1
) cc ON TRUE
WHERE t.usage_start_time >= '{{start_date}}'
  AND t.usage_start_time < '{{end_date}}'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.roaming_destination_id = 87
  AND COALESCE(t.act_usage_unit, 0) > 0
  AND t.opposite_number IS NOT NULL
  AND BTRIM(t.opposite_number::text) NOT IN ('', 'None', 'none')
  AND BTRIM(t.opposite_number::text) NOT LIKE '60%'
GROUP BY COALESCE(cc.country, 'UNMAPPED')
ORDER BY country;

Output columns:
- service_type
- charge_type
- country
- call_count
- mou_mins

Included records:
- usage_logs records within the reporting window using usage_start_time
- rat_type = 'VO'
- service_type_sub_cd = 'MO'
- roaming_destination_id = 87
- act_usage_unit > 0
- opposite_number present and not starting with '60'

Output values:
- service_type = 'Voice'
- charge_type = 'Voice MO'

Country is derived from the country_code collection using longest-prefix
matching on opposite_number.
*/

db.{{usage_log}}.aggregate([
  {
    $match: {
      usage_start_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "VO",
      service_type_sub_cd: "MO",
      roaming_destination_id: 87,
      act_usage_unit: { $gt: 0 },
      opposite_number: { $exists: true, $ne: null }
    }
  },
  {
    $addFields: {
      opposite_number_digits: {
        $trim: {
          input: { $toString: "$opposite_number" }
        }
      }
    }
  },
  {
    $match: {
      opposite_number_digits: {
        $nin: ["", "None", "none"]
      }
    }
  },
  {
    $match: {
      opposite_number_digits: { $not: { $regex: "^60" } }
    }
  },
  {
    $lookup: {
      from: "{{country_code}}",
      let: {
        destination_number: "$opposite_number_digits"
      },
      pipeline: [
        {
          $project: {
            _id: 0,
            country: 1,
            country_code_str: { $toString: "$country_code" },
            code_length: { $strLenCP: { $toString: "$country_code" } }
          }
        },
        {
          $match: {
            $expr: {
              $regexMatch: {
                input: "$$destination_number",
                regex: { $concat: ["^", "$country_code_str"] }
              }
            }
          }
        },
        {
          $sort: {
            code_length: -1
          }
        },
        {
          $limit: 1
        }
      ],
      as: "country_match"
    }
  },
  {
    $addFields: {
      country: { $ifNull: [{ $arrayElemAt: ["$country_match.country", 0] }, "UNMAPPED"] }
    }
  },
  {
    $group: {
      _id: "$country",
      call_count: { $sum: 1 },
      mou_mins: {
        $sum: {
          $divide: [
            { $toDouble: { $ifNull: ["$act_usage_unit", 0] } },
            60
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Voice" },
      charge_type: { $literal: "Voice MO" },
      country: "$_id",
      call_count: 1,
      mou_mins: { $round: ["$mou_mins", 2] }
    }
  },
  {
    $sort: {
      country: 1
    }
  }
]);
