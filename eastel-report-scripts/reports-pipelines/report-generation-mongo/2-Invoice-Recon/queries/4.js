/*
Query 4: Domestic MO voice on-net and off-net MOU.

Output:
{
  onnet_mou: 113860,
  offnet_mou: 449821
}

Equivalent PostgreSQL:

SELECT
    ROUND(
        SUM(
            CASE
                WHEN t.rating_group = 'ONNET' THEN t.act_usage_unit / 60.0
                ELSE 0
            END
        ),
        2
    ) AS onnet_mou,
    ROUND(
        SUM(
            CASE
                WHEN t.rating_group = 'OFFNET' THEN t.act_usage_unit / 60.0
                ELSE 0
            END
        ),
        2
    ) AS offnet_mou
FROM iot_portal_tb_usage_log t
WHERE t.usage_start_time >= '2026-04-01'
  AND t.usage_start_time < '2026-05-01'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.rating_group IN ('ONNET', 'OFFNET')
  AND t.roaming_destination_id = 87
  AND t.opposite_number LIKE '60%'
  AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) > 10;
*/

db.usage_logs.aggregate([
  {
    $match: {
      usage_start_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "VO",
      service_type_sub_cd: "MO",
      rating_group: { $in: ["ONNET", "OFFNET"] },
      roaming_destination_id: 87,
      opposite_number: { $regex: "^60" },
      $expr: {
        $gt: [
          { $strLenCP: { $ifNull: ["$opposite_number", ""] } },
          10
        ]
      }
    }
  },
  {
    $group: {
      _id: null,
      onnet_mou: {
        $sum: {
          $cond: [
            { $eq: ["$rating_group", "ONNET"] },
            {
              $round: [
                {
                  $divide: [
                    { $toDouble: { $ifNull: ["$act_usage_unit", 0] } },
                    60
                  ]
                },
                2
              ]
            },
            0
          ]
        }
      },
      offnet_mou: {
        $sum: {
          $cond: [
            { $eq: ["$rating_group", "OFFNET"] },
            {
              $round: [
                {
                  $divide: [
                    { $toDouble: { $ifNull: ["$act_usage_unit", 0] } },
                    60
                  ]
                },
                2
              ]
            },
            0
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      onnet_mou: 1,
      offnet_mou: 1
    }
  }
]);
